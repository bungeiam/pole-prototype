import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.models.ai_assist import AiAssistItem, AiAssistResult
from app.models.match import PoleMatch
from app.models.pole import DetectedPoleRow


class AiAssistService:
    AZURE_OPENAI_API_VERSION = "2024-02-15-preview"
    AZURE_OPENAI_TIMEOUT_SECONDS = 30

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
        input_rows: list[dict[str, Any]] = []

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
                    "match": (
                        {
                            "status": match.status,
                            "score": match.score,
                            "reason": match.reason,
                            "suggested_pool_id": match.suggested_pool_id,
                            "alternatives": match.alternatives,
                        }
                        if match
                        else None
                    ),
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
- Do NOT ignore guying requirements.
- If guying information is missing, manual review is required.
- Phase spacing is an important matching factor.
- If critical information is missing, mark requires_manual_review as true.
- Explain what is uncertain and what needs manual verification.
- Return reasons in Finnish.
- Return ONLY valid JSON. Do not use markdown.

Analyze these detected pole rows and matcher results.

Return JSON in this exact structure:
{{
  "summary": "short summary in Finnish",
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
    def _call_azure_openai(prompt: str) -> dict[str, Any]:
        endpoint = settings.azure_openai_endpoint.rstrip("/")
        deployment = settings.azure_openai_deployment

        url = (
            f"{endpoint}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={AiAssistService.AZURE_OPENAI_API_VERSION}"
        )

        body = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a careful AI assistant for technical tender data review. "
                        "You only return valid JSON."
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
            with urllib.request.urlopen(
                request,
                timeout=AiAssistService.AZURE_OPENAI_TIMEOUT_SECONDS,
            ) as response:
                raw = response.read().decode("utf-8")

        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Azure OpenAI HTTP {exc.code}: {details}") from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(f"Azure OpenAI connection failed: {exc.reason}") from exc

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            return AiAssistService._loads_json_content(content)

        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Azure OpenAI returned invalid JSON response") from exc

    @staticmethod
    def _loads_json_content(content: str) -> dict[str, Any]:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        return json.loads(cleaned)

    @staticmethod
    def _parse_ai_response(
        document_id: str,
        rows: list[DetectedPoleRow],
        payload: dict[str, Any],
    ) -> AiAssistResult:
        if not isinstance(payload, dict):
            raise ValueError("AI response root is not an object")

        payload_items = payload.get("items")
        if not isinstance(payload_items, list):
            raise ValueError("AI response does not contain items list")

        valid_row_ids = {row.row_id for row in rows}
        items: list[AiAssistItem] = []

        for item in payload_items:
            if not isinstance(item, dict):
                continue

            row_id = item.get("row_id")
            if row_id not in valid_row_ids:
                continue

            items.append(
                AiAssistItem(
                    row_id=row_id,
                    suggested_pole_type=item.get("suggested_pole_type"),
                    suggested_guying=item.get("suggested_guying"),
                    suggested_phase_spacing_m=AiAssistService._to_optional_float(
                        item.get("suggested_phase_spacing_m")
                    ),
                    confidence=AiAssistService._clamp_confidence(
                        item.get("confidence")
                    ),
                    requires_manual_review=bool(
                        item.get("requires_manual_review", True)
                    ),
                    reasons=AiAssistService._to_reason_list(item.get("reasons")),
                )
            )

        existing_ids = {item.row_id for item in items}

        for row in rows:
            if row.row_id not in existing_ids:
                items.append(
                    AiAssistService._fallback_item(
                        row=row,
                        extra_reason="AI ei palauttanut analyysiä tälle riville",
                    )
                )

        return AiAssistResult(
            document_id=document_id,
            items=items,
            summary=str(payload.get("summary") or "AI assist completed"),
        )

    @staticmethod
    def _to_optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(confidence, 1.0))

    @staticmethod
    def _to_reason_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        return [str(reason) for reason in value if reason is not None]

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
            confidence=min(row.confidence, 0.5),
            requires_manual_review=True,
            reasons=reasons,
        )