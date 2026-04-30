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
                matches=matches,
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
                matches=matches,
                summary="Azure OpenAI configuration missing",
            )

        try:
            prompt = AiAssistService._build_prompt(rows, matches)
            payload = AiAssistService._call_azure_openai(prompt)
            return AiAssistService._parse_ai_response(
                document_id=document_id,
                rows=rows,
                matches=matches,
                payload=payload,
            )
        except Exception as exc:
            return AiAssistService._fallback_result(
                document_id=document_id,
                rows=rows,
                matches=matches,
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
Olet voimajohtoprojektien tarjouslaskennan AI-avustaja ja pylvästietojen tarkastaja.

Tärkein tehtäväsi:
- auta asiantuntijaa ymmärtämään, miksi pylväsrivi on varma, epävarma tai riskialtis
- selitä puuttuvat, ristiriitaiset ja poikkeavat tiedot
- älä tee lopullista päätöstä
- älä hyväksy matchia käyttäjän puolesta
- älä keksi puuttuvia arvoja

KAIKKI käyttäjälle näkyvä teksti pitää olla suomeksi:
- summary suomeksi
- reasons-listan kaikki syyt suomeksi
- ei englanninkielisiä selityksiä

DOMAIN-SÄÄNNÖT:

1. Pylvästyyppi on keskeinen matching-tekijä.
2. Vaiheväli on keskeinen matching-tekijä.
3. Harustus on kriittinen matching-tekijä.
4. Jos harustieto on annettu, sen on täsmättävä.
5. Jos harustieto puuttuu, rivi vaatii manuaalisen tarkistuksen.
6. Jos vaiheväli puuttuu, rivi vaatii manuaalisen tarkistuksen.
7. Jos pylvästyyppi puuttuu, rivi vaatii manuaalisen tarkistuksen.
8. Jos matcher-status on ambiguous, selitä AINA mikä tekee vastaavuudesta osittaisen.
9. Jos matcher-status on unmatched, selitä AINA miksi riviä ei voitu yhdistää.
10. Älä käytä pelkkää ilmaisua "Osittainen vastaavuus" ilman tarkempaa selitystä.
11. Jos suggested_pool_id on null, älä sano että matcher ehdottaa poolia.

CONFIDENCE-SÄÄNNÖT:

- 0.90–1.00: kaikki kriittiset tiedot ovat mukana ja matcher pitää vastaavuutta varmana
- 0.70–0.85: tiedot ovat pääosin kunnossa, mutta mukana on lievä epävarmuus
- 0.50–0.70: osittainen vastaavuus tai kriittinen tieto puuttuu
- alle 0.50: kriittinen puute tai selvä ristiriita

ENIMMÄISCONFIDENCE:

- jos pole_type puuttuu → confidence saa olla enintään 0.45
- jos phase_spacing_m puuttuu → confidence saa olla enintään 0.65
- jos guying puuttuu → confidence saa olla enintään 0.65
- jos match.status on unmatched → confidence saa olla enintään 0.50
- jos match.status on ambiguous → confidence saa olla enintään 0.75
- jos harustuksessa on ristiriita → confidence saa olla enintään 0.45

requires_manual_review:

- true, jos match.status on ambiguous
- true, jos match.status on unmatched
- true, jos pole_type puuttuu
- true, jos phase_spacing_m puuttuu
- true, jos guying puuttuu
- true, jos review_status ei ole ok
- false vain jos rivi on selkeä, kriittiset tiedot ovat mukana ja matcher-status on matched

Palauta AINOASTAAN validia JSONia tässä muodossa:

{{
  "summary": "lyhyt suomenkielinen yhteenveto",
  "items": [
    {{
      "row_id": "sama row_id kuin inputissa",
      "suggested_pole_type": null,
      "suggested_guying": null,
      "suggested_phase_spacing_m": null,
      "confidence": 0.0,
      "requires_manual_review": true,
      "reasons": [
        "suomenkielinen syy 1",
        "suomenkielinen syy 2"
      ]
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
                        "Olet tarkka teknisen tarjousaineiston AI-avustaja. "
                        "Palauta vain validia JSONia. "
                        "Kaikki käyttäjälle näkyvä teksti JSONissa pitää kirjoittaa suomeksi. "
                        "Älä tee lopullisia päätöksiä, älä hyväksy matcheja ja älä keksi puuttuvia arvoja."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
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
        matches: list[PoleMatch],
        payload: dict,
    ) -> AiAssistResult:
        row_by_id = {row.row_id: row for row in rows}
        match_by_row_id = {match.row_id: match for match in matches}
        valid_row_ids = set(row_by_id.keys())
        items: list[AiAssistItem] = []

        for item in payload.get("items", []):
            row_id = item.get("row_id")

            if row_id not in valid_row_ids:
                continue

            row = row_by_id[row_id]
            match = match_by_row_id.get(row_id)

            ai_confidence = float(item.get("confidence") or 0.0)
            confidence = AiAssistService._apply_confidence_rules(
                row=row,
                match=match,
                ai_confidence=ai_confidence,
            )

            reasons = list(item.get("reasons") or [])
            reasons = AiAssistService._sanitize_ai_reasons(
                reasons=reasons,
                match=match,
            )
            reasons = AiAssistService._ensure_domain_reasons(
                row=row,
                match=match,
                reasons=reasons,
            )

            requires_manual_review = bool(item.get("requires_manual_review", True))

            if AiAssistService._row_requires_manual_review(row=row, match=match):
                requires_manual_review = True

            items.append(
                AiAssistItem(
                    row_id=row_id,
                    suggested_pole_type=item.get("suggested_pole_type"),
                    suggested_guying=item.get("suggested_guying"),
                    suggested_phase_spacing_m=item.get("suggested_phase_spacing_m"),
                    confidence=confidence,
                    requires_manual_review=requires_manual_review,
                    reasons=reasons,
                )
            )

        existing_ids = {item.row_id for item in items}

        for row in rows:
            if row.row_id not in existing_ids:
                match = match_by_row_id.get(row.row_id)
                items.append(
                    AiAssistService._fallback_item(
                        row=row,
                        match=match,
                        extra_reason="AI ei palauttanut analyysiä tälle riville",
                    )
                )

        return AiAssistResult(
            document_id=document_id,
            items=items,
            summary=payload.get("summary") or "AI-avustus valmis",
        )

    @staticmethod
    def _sanitize_ai_reasons(
        reasons: list[str],
        match: PoleMatch | None,
    ) -> list[str]:
        cleaned: list[str] = []

        for reason in reasons:
            if not reason:
                continue

            normalized = str(reason).strip()

            if not normalized:
                continue

            if (
                match
                and match.suggested_pool_id is None
                and "Matcher ehdottaa poolia" in normalized
            ):
                continue

            if (
                match
                and match.status == "unmatched"
                and "osittaiseksi" in normalized.lower()
            ):
                continue

            cleaned.append(normalized)

        return cleaned

    @staticmethod
    def _apply_confidence_rules(
        row: DetectedPoleRow,
        match: PoleMatch | None,
        ai_confidence: float,
    ) -> float:
        if ai_confidence <= 0.0:
            confidence = AiAssistService._calculate_minimum_confidence(row)
        else:
            confidence = ai_confidence

        confidence = max(0.0, min(confidence, 1.0))

        if not row.pole_type:
            confidence = min(confidence, 0.45)

        if row.guying is None:
            confidence = min(confidence, 0.65)

        if row.span_m is None:
            confidence = min(confidence, 0.65)

        if match and match.status == "unmatched":
            confidence = min(confidence, 0.50)

        if match and match.status == "ambiguous":
            confidence = min(confidence, 0.75)

        return confidence

    @staticmethod
    def _calculate_minimum_confidence(row: DetectedPoleRow) -> float:
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

        return min(confidence, 0.85)

    @staticmethod
    def _row_requires_manual_review(
        row: DetectedPoleRow,
        match: PoleMatch | None,
    ) -> bool:
        if row.review_status != "ok":
            return True

        if not row.pole_type:
            return True

        if row.span_m is None:
            return True

        if row.guying is None:
            return True

        if match and match.status in {"ambiguous", "unmatched"}:
            return True

        return False

    @staticmethod
    def _ensure_domain_reasons(
        row: DetectedPoleRow,
        match: PoleMatch | None,
        reasons: list[str],
    ) -> list[str]:
        clean_reasons = [reason for reason in reasons if reason]

        if row.pole_type:
            clean_reasons.append(f"Pylvästyyppi tunnistettu: {row.pole_type}")
        else:
            clean_reasons.append("Pylvästyyppi puuttuu – vaatii manuaalisen tarkistuksen")

        if row.support_height_m is not None:
            clean_reasons.append(f"Pylväskorkeus tunnistettu: {row.support_height_m} m")
        else:
            clean_reasons.append("Pylväskorkeus puuttuu tai on epävarma")

        if row.span_m is not None:
            clean_reasons.append(f"Vaiheväli tunnistettu: {row.span_m} m")
        else:
            clean_reasons.append("Vaiheväli puuttuu – kriittinen matching-tieto")

        if row.guying is not None:
            clean_reasons.append(f"Harustieto tunnistettu: {row.guying}")
        else:
            clean_reasons.append("Harustieto puuttuu – vaatii manuaalisen tarkistuksen")

        if match:
            if match.status == "matched":
                clean_reasons.append("Matcher löysi varman vastaavuuden.")

                if match.suggested_pool_id:
                    clean_reasons.append(
                        f"Matcherin ehdottama pooli: {match.suggested_pool_id}"
                    )

            elif match.status == "ambiguous":
                clean_reasons.append(
                    "Matcher löysi vain osittaisen vastaavuuden, joten rivi vaatii asiantuntijan tarkistuksen."
                )

                if match.suggested_pool_id:
                    clean_reasons.append(
                        f"Matcherin ehdottama tarkistettava pooli: {match.suggested_pool_id}"
                    )
                else:
                    clean_reasons.append(
                        "Matcher ei antanut yksiselitteistä pooliehdotusta."
                    )

                if match.reason:
                    clean_reasons.append(f"Matcherin syy: {match.reason}")

            elif match.status == "unmatched":
                clean_reasons.append(
                    "Matcher ei löytänyt hyväksyttävää poolivastaavuutta."
                )

                if match.reason:
                    clean_reasons.append(f"Matcherin syy: {match.reason}")

                if match.alternatives:
                    clean_reasons.append(
                        "Mahdollisia lähimpiä vaihtoehtoja tarkistukseen: "
                        + ", ".join(match.alternatives)
                    )
        else:
            clean_reasons.append("Matcher-tulosta ei ole saatavilla tälle riville.")

        if row.review_status != "ok":
            clean_reasons.append(
                f"Rivin tarkistustila on {row.review_status}, joten rivi vaatii tarkistuksen"
            )

        return AiAssistService._deduplicate_reasons(clean_reasons)

    @staticmethod
    def _deduplicate_reasons(reasons: list[str]) -> list[str]:
        seen = set()
        result = []

        for reason in reasons:
            normalized = reason.strip()

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(normalized)

        return result

    @staticmethod
    def _fallback_result(
        document_id: str,
        rows: list[DetectedPoleRow],
        matches: list[PoleMatch],
        summary: str,
    ) -> AiAssistResult:
        match_by_row_id = {match.row_id: match for match in matches}

        return AiAssistResult(
            document_id=document_id,
            summary=summary,
            items=[
                AiAssistService._fallback_item(
                    row=row,
                    match=match_by_row_id.get(row.row_id),
                    extra_reason=summary,
                )
                for row in rows
            ],
        )

    @staticmethod
    def _fallback_item(
        row: DetectedPoleRow,
        match: PoleMatch | None,
        extra_reason: str,
    ) -> AiAssistItem:
        reasons = [extra_reason]

        if not row.pole_type:
            reasons.append("Pylvästyyppi puuttuu – vaatii manuaalisen tarkistuksen")

        if row.guying is None:
            reasons.append("Harustieto puuttuu – vaatii manuaalisen tarkistuksen")

        if row.span_m is None:
            reasons.append("Vaiheväli puuttuu – kriittinen matching-tieto")

        if row.review_status != "ok":
            reasons.append(f"Rivin tarkistustila on {row.review_status}")

        reasons = AiAssistService._ensure_domain_reasons(
            row=row,
            match=match,
            reasons=reasons,
        )

        return AiAssistItem(
            row_id=row.row_id,
            suggested_pole_type=row.pole_type,
            suggested_guying=row.guying,
            suggested_phase_spacing_m=row.span_m,
            confidence=AiAssistService._apply_confidence_rules(
                row=row,
                match=match,
                ai_confidence=min(row.confidence, 0.5),
            ),
            requires_manual_review=True,
            reasons=reasons,
        )