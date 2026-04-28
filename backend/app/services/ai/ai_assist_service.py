import json
import urllib.error
import urllib.request

from app.core.config import settings
from app.models.ai_assist import AiAssistItem, AiAssistResult
from app.models.match import PoleMatch
from app.models.pole import DetectedPoleRow


class AiAssistService:
    @staticmethod
    def analyze(
        document_id: str,
        rows: list[DetectedPoleRow],
        matches: list[PoleMatch] | None = None,
    ) -> AiAssistResult:
        matches = matches or []

        if not settings.use_azure_openai:
            return AiAssistService._fallback_result(
                document_id=document_id,
                rows=rows,
                summary="AI not enabled",
            )

        if (
            not settings.azure_openai_endpoint
            or not settings.azure_openai_key
            or not settings.azure_openai_deployment
        ):
            return AiAssistService._fallback_result(
                document_id=document_id,
                rows=rows,
                summary="Azure OpenAI configuration missing",
            )

        try:
            prompt = AiAssistService._build_prompt(rows, matches)
            payload = AiAssistService._call_azure_openai(prompt)
            return AiAssistService._parse_ai_response(document_id, rows, payload)
        except Exception as exc:
            return AiAssistService._fallback_result(
                document_id=document_id,
                rows=rows,
                summary=f"AI assist failed: {exc}",
            )

    @staticmethod
    def _build_prompt(rows: list[DetectedPoleRow], matches: list[PoleMatch]) -> str:
        match_by_row_id = {match.row_id: match for match in matches}
        input_rows = []

        for row in rows:
            match = match_by_row_id.get(row.row_id)
            input_rows.append(
                {
                    "row_id": row.row_id,
                    "pole_code": row.pole_code,
                    "pole_type": row.pole_type,
                    "support_height_m": row.support_height_m,
                    "phase_spacing_m": row.span_m,
                    "guying": row.guying,
                    "quantity": row.quantity,
                    "row_confidence": row.confidence,
                    "review_status": row.review_status,
                    "raw_data": row.raw_data,
                    "match": {
                        "status": match.status,
                        "score": match.score,
                        "reason": match.reason,
                        "suggested_pool_id": match.suggested_pool_id,
                        "alternatives": match.alternatives,
                    }
                    if match
                    else None,
                }
            )

        return f"""
You are an AI assistant supporting power line tender calculation.

Your role:
- Help the human expert understand uncertain pole rows.
- Explain missing or unclear information.
- Suggest possible interpretations only when the source data supports them.
- Always keep the human expert responsible for final decisions.

Important rules:
- Do NOT select the final pole.
- Do NOT approve any match.
- Do NOT override the matcher.
- Do NOT invent missing values.
- All user-facing text must be Finnish.
- Summary must be Finnish.
- Every reason in reasons must be Finnish.
- Do not write English explanations in summary or reasons.
- Phase spacing is an important matching factor.
- Guying is a critical matching factor.

Analyze these detected pole rows and matcher results.

Return ONLY valid JSON in this exact structure:
{{
  "summary": "short summary",
  "items": [
    {{
      "row_id": "same row_id as input",
      "suggested_pole_type": null,
      "suggested_guying": null,
      "suggested_phase_spacing_m": null,
      "confidence": 0.0,
      "requires_manual_review": true,
      "reasons": ["reason 1", "reason 2"]
    }}
  ]
}}

Input:
{json.dumps(input_rows, ensure_ascii=False, indent=2)}
""".strip()

    @staticmethod
    def _call_azure_openai(prompt: str) -> dict:
        endpoint = settings.azure_openai_endpoint.rstrip("/")
        deployment = settings.azure_openai_deployment

        url = (
            f"{endpoint}/openai/deployments/{deployment}/chat/completions"
            "?api-version=2024-02-15-preview"
        )

        body = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a careful AI assistant for technical tender data review. "
                        "Return only valid JSON. "
                        "All user-facing text in the JSON must be Finnish. "
                        "The summary and every item in reasons must be written in Finnish."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }

        request = urllib.request.Request(
            url=url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-key": settings.azure_openai_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Azure OpenAI HTTP {exc.code}: {details}") from exc

        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    @staticmethod
    def _parse_ai_response(
        document_id: str,
        rows: list[DetectedPoleRow],
        payload: dict,
    ) -> AiAssistResult:
        row_by_id = {row.row_id: row for row in rows}
        valid_row_ids = set(row_by_id.keys())
        items: list[AiAssistItem] = []

        for item in payload.get("items", []):
            row_id = item.get("row_id")

            if row_id not in valid_row_ids:
                continue

            row = row_by_id[row_id]
            ai_confidence = float(item.get("confidence") or 0.0)
            confidence = AiAssistService._apply_minimum_confidence_fallback(
                row=row,
                ai_confidence=ai_confidence,
            )

            items.append(
                AiAssistItem(
                    row_id=row_id,
                    suggested_pole_type=item.get("suggested_pole_type"),
                    suggested_guying=item.get("suggested_guying"),
                    suggested_phase_spacing_m=item.get("suggested_phase_spacing_m"),
                    confidence=confidence,
                    requires_manual_review=bool(
                        item.get("requires_manual_review", True)
                    ),
                    reasons=list(item.get("reasons") or []),
                )
            )

        existing_ids = {item.row_id for item in items}

        for row in rows:
            if row.row_id not in existing_ids:
                items.append(
                    AiAssistService._fallback_item(
                        row=row,
                        extra_reason="AI did not return analysis for this row",
                    )
                )

        return AiAssistResult(
            document_id=document_id,
            items=items,
            summary=payload.get("summary") or "AI assist completed",
        )

    @staticmethod
    def _apply_minimum_confidence_fallback(
        row: DetectedPoleRow,
        ai_confidence: float,
    ) -> float:
        if ai_confidence > 0.0:
            return ai_confidence

        confidence = 0.0

        if row.pole_type:
            confidence += 0.25

        if row.support_height_m is not None:
            confidence += 0.20

        if row.span_m is not None:
            confidence += 0.20

        if row.guying is not None:
            confidence += 0.20

        if row.quantity is not None:
            confidence += 0.10

        if row.review_status == "ok":
            confidence += 0.10

        confidence = min(confidence, 0.85)

        if not row.pole_type:
            confidence = min(confidence, 0.45)

        if row.guying is None:
            confidence = min(confidence, 0.65)

        if row.span_m is None:
            confidence = min(confidence, 0.65)

        return confidence

    @staticmethod
    def _fallback_result(
        document_id: str,
        rows: list[DetectedPoleRow],
        summary: str,
    ) -> AiAssistResult:
        return AiAssistResult(
            document_id=document_id,
            summary=summary,
            items=[
                AiAssistService._fallback_item(row=row, extra_reason=summary)
                for row in rows
            ],
        )

    @staticmethod
    def _fallback_item(row: DetectedPoleRow, extra_reason: str) -> AiAssistItem:
        reasons = [extra_reason]

        if not row.pole_type:
            reasons.append("Pylvästyyppi puuttuu")

        if row.guying is None:
            reasons.append("Harustieto puuttuu – vaatii manuaalisen tarkistuksen")

        if row.span_m is None:
            reasons.append("Vaiheväli puuttuu tai on epävarma")

        if row.review_status != "ok":
            reasons.append(f"Rivin tarkistustila on {row.review_status}")

        return AiAssistItem(
            row_id=row.row_id,
            suggested_pole_type=row.pole_type,
            suggested_guying=row.guying,
            suggested_phase_spacing_m=row.span_m,
            confidence=AiAssistService._apply_minimum_confidence_fallback(
                row=row,
                ai_confidence=min(row.confidence, 0.5),
            ),
            requires_manual_review=True,
            reasons=reasons,
        )