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
                summary="AI ei ole käytössä. Selitykset muodostettiin sääntöpohjaisesti.",
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
                summary="Azure OpenAI -asetukset puuttuvat. Selitykset muodostettiin sääntöpohjaisesti.",
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
                summary=f"AI-selitys epäonnistui. Selitykset muodostettiin sääntöpohjaisesti. Virhe: {exc}",
            )

    @staticmethod
    def _build_prompt(rows: list[DetectedPoleRow], matches: list[PoleMatch]) -> str:
        match_by_row_id = {match.row_id: match for match in matches}

        input_rows = []
        for row in rows:
            match = match_by_row_id.get(row.row_id)

            input_rows.append(
                {
                    "detected_pole_row": {
                        "row_id": row.row_id,
                        "document_id": row.document_id,
                        "source_sheet": row.source_sheet,
                        "source_row_number": row.source_row_number,
                        "pole_code": row.pole_code,
                        "pole_type": row.pole_type,
                        "support_height_m": row.support_height_m,
                        "span_m": row.span_m,
                        "guying": row.guying,
                        "quantity": row.quantity,
                        "row_confidence": row.confidence,
                        "review_status": row.review_status,
                        "raw_data": row.raw_data,
                    },
                    "pole_match": {
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
Tehtävä:
Muodosta käyttäjälle selitys siitä, miten sääntöpohjainen pylväsmatcher tulkitsi asiakkaan aineistosta tunnistetun pylväsrivin.

Roolitus:
- DetectedPoleRow kuvaa asiakkaan aineistosta tunnistettua pylväsriviä.
- PoleMatch kuvaa erillisen matcher-logiikan tuottamaa tulosta.
- Selitys on asiantuntijan tarkistusta varten.
- Selitys ei muuta matcherin tulosta.

Käyttäjälle tuotetaan suomenkielinen JSON-yhteenveto, jossa jokaiselle riville kerrotaan:
- mitkä asiat vaikuttivat tulokseen
- miksi rivi vaatii tai ei vaadi manuaalista tarkistusta
- mitä käyttäjän kannattaa tarkistaa seuraavaksi

Tekninen tulkintalogiikka:
- Pylvästyyppi on tärkeä vastaavuuden arvioinnissa.
- Vaiheväli on tärkeä vastaavuuden arvioinnissa.
- Harustus on kriittinen tieto silloin, kun se on annettu.
- Jos harustieto puuttuu, rivi kannattaa ohjata manuaaliseen tarkistukseen.
- Jos vaiheväli puuttuu, rivi kannattaa ohjata manuaaliseen tarkistukseen.
- Jos pylvästyyppi puuttuu, rivi kannattaa ohjata manuaaliseen tarkistukseen.
- Jos match_status on ambiguous, selityksen tulee kertoa, miksi vastaavuus jäi epävarmaksi.
- Jos match_status on unmatched, selityksen tulee kertoa, miksi hyväksyttävää vastaavuutta ei löytynyt.
- Jos matcher on antanut reason-kentän, hyödynnä sitä selityksessä.

Match-statusten selitystapa:
- matched: matcher löysi vastaavuuden. Mainitse silti mahdolliset puuttuvat kriittiset tiedot.
- ambiguous: vastaavuus jäi epävarmaksi. Kerro, mitkä tiedot kannattaa tarkistaa.
- unmatched: hyväksyttävää vastaavuutta ei löytynyt. Kerro mahdolliset tarkistuskohteet.

Confidence-ohje:
- 0.90–1.00: kaikki kriittiset tiedot ovat mukana ja match on selkeä.
- 0.70–0.85: tiedot ovat pääosin kunnossa, mutta mukana on lievä epävarmuus.
- 0.50–0.70: osittainen vastaavuus tai kriittinen tieto puuttuu.
- alle 0.50: kriittinen puute, unmatched-tulos tai selvä ristiriita.

Rajoitukset confidence-arvolle:
- jos pole_type puuttuu, confidence enintään 0.45
- jos span_m puuttuu, confidence enintään 0.65
- jos guying puuttuu, confidence enintään 0.65
- jos match.status on unmatched, confidence enintään 0.50
- jos match.status on ambiguous, confidence enintään 0.75

requires_manual_review on true, jos:
- match.status on ambiguous
- match.status on unmatched
- pole_type puuttuu
- span_m puuttuu
- guying puuttuu
- review_status ei ole ok

Palauta JSON seuraavassa rakenteessa:

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

Analysoitavat rivit:
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
                        "Laadi tekninen JSON-muotoinen selitys pylväsmatcherin tuloksista. "
                        "Käytä suomea. Vastauksen tulee olla validia JSONia."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.1,
            "max_tokens": 3000,
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

            ai_confidence = AiAssistService._safe_float(item.get("confidence"), default=0.0)

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
                    suggested_pole_type=None,
                    suggested_guying=None,
                    suggested_phase_spacing_m=None,
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
                        extra_reason="AI ei palauttanut analyysiä tälle riville.",
                    )
                )

        return AiAssistResult(
            document_id=document_id,
            items=items,
            summary=payload.get("summary") or "AI-selitys matcherin tuloksista valmis.",
        )

    @staticmethod
    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

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

            lowered = normalized.lower()

            if match and match.suggested_pool_id is None:
                if "matcher ehdottaa poolia" in lowered:
                    continue
                if "ehdotettu pooli" in lowered:
                    continue
                if "suggested_pool_id" in lowered and "null" not in lowered:
                    continue

            if match and match.status == "unmatched":
                if "varma vastaavuus" in lowered:
                    continue
                if "hyväksytty vastaavuus" in lowered:
                    continue
                if "osittainen vastaavuus" in lowered:
                    continue

            if match and match.status == "ambiguous":
                if normalized.strip().lower() == "osittainen vastaavuus":
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

        if match is None:
            return True

        return False

    @staticmethod
    def _ensure_domain_reasons(
        row: DetectedPoleRow,
        match: PoleMatch | None,
        reasons: list[str],
    ) -> list[str]:
        clean_reasons = [reason for reason in reasons if reason]

        clean_reasons.extend(
            AiAssistService._build_detected_row_reasons(row=row)
        )

        clean_reasons.extend(
            AiAssistService._build_match_explanation_reasons(
                row=row,
                match=match,
            )
        )

        if row.review_status != "ok":
            clean_reasons.append(
                f"Rivin tarkistustila on {row.review_status}, joten rivi vaatii asiantuntijan tarkistuksen."
            )

        if AiAssistService._row_requires_manual_review(row=row, match=match):
            clean_reasons.append(
                "Rivi vaatii manuaalisen tarkistuksen ennen kuin sitä voidaan käyttää laskennan lopullisena perusteena."
            )
        else:
            clean_reasons.append(
                "Rivillä on tarvittavat kriittiset tiedot ja matcher löysi vastaavuuden, mutta käyttäjän tulee silti tarkistaa tulos ennen hyväksyntää."
            )

        return AiAssistService._deduplicate_reasons(clean_reasons)

    @staticmethod
    def _build_detected_row_reasons(row: DetectedPoleRow) -> list[str]:
        reasons: list[str] = []

        if row.pole_type:
            reasons.append(f"Pylvästyyppi tunnistettu: {row.pole_type}.")
        else:
            reasons.append("Pylvästyyppi puuttuu. Tarkista asiakkaan aineistosta pylvään tyyppimerkintä tai mahdollinen tyyppimapping.")

        if row.support_height_m is not None:
            reasons.append(f"Pylväskorkeus tunnistettu: {row.support_height_m} m.")
        else:
            reasons.append("Pylväskorkeus puuttuu tai on epävarma. Tarkista korkeustieto ennen lopullista massalaskentaa.")

        if row.span_m is not None:
            reasons.append(f"Vaiheväli tunnistettu: {row.span_m} m.")
        else:
            reasons.append("Vaiheväli puuttuu. Vaiheväli on keskeinen matching-tieto ja vaatii manuaalisen tarkistuksen.")

        if row.guying is not None:
            reasons.append(f"Harustieto tunnistettu: {row.guying}.")
        else:
            reasons.append("Harustieto puuttuu. Harustus on kriittinen ehto ja vaatii manuaalisen tarkistuksen.")

        if row.quantity is not None:
            reasons.append(f"Määrä tunnistettu: {row.quantity}.")
        else:
            reasons.append("Määrätieto puuttuu tai on epävarma.")

        return reasons

    @staticmethod
    def _build_match_explanation_reasons(
        row: DetectedPoleRow,
        match: PoleMatch | None,
    ) -> list[str]:
        if match is None:
            return [
                "Matcher-tulosta ei ole saatavilla tälle riville.",
                "Tarkista, onko rivi mukana matcher-ajossa ja sisältääkö se riittävät lähtötiedot.",
            ]

        if match.status == "matched":
            return AiAssistService._explain_matched(row=row, match=match)

        if match.status == "ambiguous":
            return AiAssistService._explain_ambiguous(row=row, match=match)

        if match.status == "unmatched":
            return AiAssistService._explain_unmatched(row=row, match=match)

        return [
            f"Matcher palautti tuntemattoman tilan: {match.status}.",
            "Tarkista matcherin tulos ennen rivin käyttöä laskennassa.",
        ]

    @staticmethod
    def _explain_matched(
        row: DetectedPoleRow,
        match: PoleMatch,
    ) -> list[str]:
        reasons: list[str] = [
            "Matcher löysi riville vastaavuuden pylväspoolista.",
            f"Matcherin pisteytys: {match.score}.",
        ]

        if match.suggested_pool_id:
            reasons.append(f"Matcherin ehdottama pooli: {match.suggested_pool_id}.")
        else:
            reasons.append("Matcherin status on matched, mutta suggested_pool_id puuttuu. Tarkista matcher-tulos.")

        if match.reason:
            reasons.append(f"Matcherin perustelu: {match.reason}")

        if not row.pole_type or row.span_m is None or row.guying is None:
            reasons.append(
                "Vaikka matcher löysi vastaavuuden, riviltä puuttuu yksi tai useampi kriittinen lähtötieto."
            )

        return reasons

    @staticmethod
    def _explain_ambiguous(
        row: DetectedPoleRow,
        match: PoleMatch,
    ) -> list[str]:
        reasons: list[str] = [
            "Matcher löysi vain epävarman tai osittaisen vastaavuuden.",
            "Riviä ei pidä hyväksyä automaattisesti, vaan asiantuntijan tulee tarkistaa lähimmät vaihtoehdot.",
            f"Matcherin pisteytys: {match.score}.",
        ]

        if match.suggested_pool_id:
            reasons.append(
                f"Matcherin lähin tarkistettava pooliehdotus: {match.suggested_pool_id}."
            )
        else:
            reasons.append(
                "Matcher ei antanut yksiselitteistä pooliehdotusta."
            )

        if match.reason:
            reasons.append(f"Matcherin perustelu epävarmuudelle: {match.reason}")

        if match.alternatives:
            reasons.append(
                "Tarkistettavia lähimpiä vaihtoehtoja: "
                + ", ".join(match.alternatives)
                + "."
            )

        if not row.pole_type:
            reasons.append("Tarkista, onko pylvästyypin mapping puutteellinen tai tyyppimerkintä kirjoitettu eri muodossa.")

        if row.support_height_m is None:
            reasons.append("Tarkista pylväskorkeus, koska korkeus voi vaikuttaa poolivastaavuuteen.")

        if row.span_m is None:
            reasons.append("Tarkista vaiheväli, koska se on keskeinen vastaavuuden arviointitekijä.")

        if row.guying is None:
            reasons.append("Tarkista harustieto, koska harustuksen puuttuminen estää varman tulkinnan.")

        return reasons

    @staticmethod
    def _explain_unmatched(
        row: DetectedPoleRow,
        match: PoleMatch,
    ) -> list[str]:
        reasons: list[str] = [
            "Matcher ei löytänyt riville hyväksyttävää pylväspoolin vastaavuutta.",
            "Rivi vaatii asiantuntijan tarkistuksen ennen kuin sitä voidaan käyttää laskennassa.",
            f"Matcherin pisteytys: {match.score}.",
        ]

        if match.reason:
            reasons.append(f"Matcherin perustelu epäonnistumiselle: {match.reason}")

        if row.pole_type:
            reasons.append(
                f"Tarkista, löytyykö pylvästyyppi {row.pole_type} pylväspoolista tai puuttuuko sille tyyppimapping."
            )
        else:
            reasons.append(
                "Tarkista pylvästyyppi asiakkaan aineistosta, koska ilman tyyppitietoa poolivastaavuutta ei voida varmistaa."
            )

        if row.support_height_m is not None:
            reasons.append(
                f"Tarkista, löytyykö poolista korkeuden {row.support_height_m} m kanssa yhteensopiva pylväs."
            )
        else:
            reasons.append(
                "Tarkista pylväskorkeus, koska puuttuva korkeus voi estää poolivastaavuuden löytymisen."
            )

        if row.span_m is not None:
            reasons.append(
                f"Tarkista vaihevälin {row.span_m} m yhteensopivuus pylväspoolin tietoihin."
            )
        else:
            reasons.append(
                "Tarkista vaiheväli, koska puuttuva vaiheväli voi estää matchin onnistumisen."
            )

        if row.guying is not None:
            reasons.append(
                f"Tarkista, että harustieto {row.guying} vastaa pylväspoolin harustusvaatimusta."
            )
        else:
            reasons.append(
                "Tarkista harustieto. Jos harustus puuttuu asiakkaan aineistosta, sitä ei saa olettaa automaattisesti."
            )

        if match.alternatives:
            reasons.append(
                "Matcher löysi mahdollisia lähimpiä vaihtoehtoja, mutta ei hyväksyttävää vastaavuutta: "
                + ", ".join(match.alternatives)
                + "."
            )

        return reasons

    @staticmethod
    def _deduplicate_reasons(reasons: list[str]) -> list[str]:
        seen = set()
        result = []

        for reason in reasons:
            normalized = str(reason).strip()
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

        reasons = AiAssistService._ensure_domain_reasons(
            row=row,
            match=match,
            reasons=reasons,
        )

        return AiAssistItem(
            row_id=row.row_id,
            suggested_pole_type=None,
            suggested_guying=None,
            suggested_phase_spacing_m=None,
            confidence=AiAssistService._apply_confidence_rules(
                row=row,
                match=match,
                ai_confidence=min(row.confidence, 0.5),
            ),
            requires_manual_review=AiAssistService._row_requires_manual_review(
                row=row,
                match=match,
            ),
            reasons=reasons,
        )