from app.models.document import OfferDocument
from app.models.pole import DetectedPoleRow
from app.models.match import PoleMatch
from app.models.calculation import MassCalculationResult
from app.models.correction import UserCorrection


DOCUMENTS: dict[str, OfferDocument] = {}
POLES_BY_DOCUMENT: dict[str, list[DetectedPoleRow]] = {}
MATCHES_BY_DOCUMENT: dict[str, list[PoleMatch]] = {}
CALCULATIONS_BY_DOCUMENT: dict[str, list[MassCalculationResult]] = {}
CORRECTIONS_BY_ROW: dict[str, UserCorrection] = {}