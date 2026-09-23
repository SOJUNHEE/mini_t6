"""표준 업로드 양식 스키마 (명세서 §5).

data/samples/axport_upload_template_v0.1.xlsx 의 구조를 선언한다.
양식 파일과 이 선언이 어긋나면 tests/test_schema_matches_template.py 가 잡는다.
양식을 바꾸면 여기와 template_version 을 함께 고친다.

`kind` 는 검증에 필요해서 여기서 선언한다. 양식 파일은 컬럼명과
필수 구분만 표현하고 타입을 표현하지 않기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TEMPLATE_VERSION = "0.1"

# 값 종류
TEXT = "text"
DATE = "date"       # YYYY-MM-DD 문자열
NUM = "num"

# 필수 구분 — 양식 2행의 대괄호 태그와 1:1 대응
COMMON_REQUIRED = "common_required"   # [공통필수]
AREA_REQUIRED = "area_required"       # [영역필수:<영역>]
OPTIONAL = "optional"                 # [선택]

TAG_TO_CLASS = {
    "공통필수": COMMON_REQUIRED,
    "영역필수": AREA_REQUIRED,
    "선택": OPTIONAL,
}

HEADER_ROW = 1
DESC_ROW = 2
DATA_START_ROW = 3

INFO_SHEET = "양식정보"
ERROR_CASE_SHEET = "오류케이스"   # 샘플 파일에만 있다
NON_DATA_SHEETS = {INFO_SHEET, ERROR_CASE_SHEET}

# 해당 없음을 뜻하는 입력. 빈칸(미입력)과 구분한다 (명세서 §4)
NOT_APPLICABLE_TOKENS = {"N/A", "n/a", "NA", "해당없음", "해당 없음"}


@dataclass(frozen=True)
class Column:
    name: str
    requirement: str
    kind: str
    area: str = ""
    non_negative: bool = False
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sheet:
    name: str
    primary_key: str
    columns: tuple[Column, ...]
    # (이 시트의 컬럼, 참조할 시트, 그 시트의 컬럼)
    references: tuple[tuple[str, str, str], ...] = ()
    # (시작일 컬럼, 종료일 컬럼) — 종료일 >= 시작일
    date_order: tuple[tuple[str, str], ...] = ()
    row_identity: tuple[str, ...] = field(default=())

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    def column(self, name: str) -> Column | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None


def _c(name, requirement, kind, area="", non_negative=False, aliases=()):
    return Column(name, requirement, kind, area, non_negative, tuple(aliases))


SHEETS: tuple[Sheet, ...] = (
    Sheet(
        name="제품정보",
        primary_key="제품ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT, aliases=("회사ID", "company_id")),
            _c("제품ID", COMMON_REQUIRED, TEXT, aliases=("품목ID", "product_id")),
            _c("모델명", COMMON_REQUIRED, TEXT, aliases=("모델", "model")),
            _c("제품군", AREA_REQUIRED, TEXT, "규제·시장성", aliases=("카테고리",)),
            _c("HS코드", AREA_REQUIRED, TEXT, "관세·규제", aliases=("HS", "HSCODE", "HS CODE", "세번")),
            _c("HS버전", AREA_REQUIRED, TEXT, "관세"),
            _c("HS적용국", OPTIONAL, TEXT, "관세"),
            _c("제조국코드", AREA_REQUIRED, TEXT, "관세·원산지", aliases=("원산지", "제조국")),
            _c("제조국명_원본", OPTIONAL, TEXT),
            _c("사양요약", OPTIONAL, TEXT),
            _c("사양서참조", OPTIONAL, TEXT),
            _c("전략물자해당", AREA_REQUIRED, TEXT, "수출규제"),
            _c("비고", OPTIONAL, TEXT),
        ),
    ),
    Sheet(
        name="수출예정거래",
        primary_key="거래ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("거래ID", COMMON_REQUIRED, TEXT, aliases=("거래번호", "deal_id")),
            _c("제품ID", COMMON_REQUIRED, TEXT),
            _c("목적국코드", COMMON_REQUIRED, TEXT, aliases=("목적국", "수출국", "대상국")),
            _c("목적국명_원본", OPTIONAL, TEXT),
            _c("거래처ID", AREA_REQUIRED, TEXT, "거래처"),
            _c("최종사용자명", AREA_REQUIRED, TEXT, "수출규제"),
            _c("최종용도", AREA_REQUIRED, TEXT, "수출규제"),
            _c("수량", AREA_REQUIRED, NUM, "수익성·공급", non_negative=True),
            _c("수량단위", AREA_REQUIRED, TEXT, "수익성·공급"),
            _c("단가", AREA_REQUIRED, NUM, "수익성", non_negative=True),
            _c("통화", AREA_REQUIRED, TEXT, "수익성"),
            _c("금액배율", AREA_REQUIRED, NUM, "수익성", non_negative=True),
            _c("납기일", AREA_REQUIRED, DATE, "공급·물류"),
            _c("인도조건", AREA_REQUIRED, TEXT, "수익성·물류", aliases=("Incoterms", "인코텀즈")),
            _c("결제조건", OPTIONAL, TEXT),
            _c("평가기준일", COMMON_REQUIRED, DATE, aliases=("기준일",)),
            _c("비고", OPTIONAL, TEXT),
        ),
        references=(
            ("제품ID", "제품정보", "제품ID"),
            ("거래처ID", "거래처", "거래처ID"),
        ),
    ),
    Sheet(
        name="수출실적",
        primary_key="실적ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("실적ID", COMMON_REQUIRED, TEXT),
            _c("거래일", COMMON_REQUIRED, DATE),
            _c("제품ID", COMMON_REQUIRED, TEXT),
            _c("거래처ID", OPTIONAL, TEXT),
            _c("목적국코드", AREA_REQUIRED, TEXT, "실적·시장성"),
            _c("수량", AREA_REQUIRED, NUM, "실적", non_negative=True),
            _c("수량단위", AREA_REQUIRED, TEXT, "실적"),
            _c("금액", AREA_REQUIRED, NUM, "실적", non_negative=True),
            _c("통화", AREA_REQUIRED, TEXT, "실적"),
            _c("금액배율", AREA_REQUIRED, NUM, "실적", non_negative=True),
            _c("취소여부", AREA_REQUIRED, TEXT, "실적"),
            _c("반품수량", OPTIONAL, NUM, non_negative=True),
            _c("비고", OPTIONAL, TEXT),
        ),
        references=(
            ("제품ID", "제품정보", "제품ID"),
            ("거래처ID", "거래처", "거래처ID"),
        ),
        row_identity=("기업ID", "실적ID", "거래일", "제품ID", "목적국코드",
                      "수량", "금액", "통화", "취소여부"),
    ),
    Sheet(
        name="원가·비용",
        primary_key="원가ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("원가ID", COMMON_REQUIRED, TEXT),
            _c("제품ID", COMMON_REQUIRED, TEXT),
            _c("기준일", AREA_REQUIRED, DATE, "수익성"),
            _c("제조원가", AREA_REQUIRED, NUM, "수익성", non_negative=True),
            _c("운송비", AREA_REQUIRED, NUM, "수익성·물류", non_negative=True),
            _c("보험료", AREA_REQUIRED, NUM, "수익성", non_negative=True),
            _c("포장비", AREA_REQUIRED, NUM, "수익성", non_negative=True),
            _c("통화", AREA_REQUIRED, TEXT, "수익성"),
            _c("금액배율", AREA_REQUIRED, NUM, "수익성", non_negative=True),
            _c("비용부담주체", AREA_REQUIRED, TEXT, "수익성"),
            _c("결제조건", OPTIONAL, TEXT),
            _c("비고", OPTIONAL, TEXT),
        ),
        references=(("제품ID", "제품정보", "제품ID"),),
    ),
    Sheet(
        name="재고·생산",
        primary_key="재고ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("재고ID", COMMON_REQUIRED, TEXT),
            _c("제품ID", COMMON_REQUIRED, TEXT),
            _c("기준일", AREA_REQUIRED, DATE, "공급"),
            _c("가용재고수량", AREA_REQUIRED, NUM, "공급", non_negative=True),
            _c("예약재고수량", AREA_REQUIRED, NUM, "공급", non_negative=True),
            _c("수량단위", AREA_REQUIRED, TEXT, "공급"),
            _c("기수주수량", AREA_REQUIRED, NUM, "공급", non_negative=True),
            _c("생산시작예정일", OPTIONAL, DATE, "공급"),
            _c("생산완료예정일", AREA_REQUIRED, DATE, "공급"),
            _c("검사소요일수", OPTIONAL, NUM, "공급", non_negative=True),
            _c("공급가능수량", AREA_REQUIRED, NUM, "공급", non_negative=True),
            _c("비고", OPTIONAL, TEXT),
        ),
        references=(("제품ID", "제품정보", "제품ID"),),
        date_order=(("생산시작예정일", "생산완료예정일"),),
    ),
    Sheet(
        name="물류",
        primary_key="물류ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("물류ID", COMMON_REQUIRED, TEXT),
            _c("거래ID", COMMON_REQUIRED, TEXT),
            _c("출발지", AREA_REQUIRED, TEXT, "물류"),
            _c("도착지", AREA_REQUIRED, TEXT, "물류"),
            _c("운송수단", AREA_REQUIRED, TEXT, "물류"),
            _c("출발예정일", AREA_REQUIRED, DATE, "물류"),
            _c("도착예정일", AREA_REQUIRED, DATE, "물류"),
            _c("출발실제일", OPTIONAL, DATE),
            _c("도착실제일", OPTIONAL, DATE),
            _c("운임", AREA_REQUIRED, NUM, "물류", non_negative=True),
            _c("통화", AREA_REQUIRED, TEXT, "물류"),
            _c("금액배율", AREA_REQUIRED, NUM, "물류", non_negative=True),
            _c("견적만료일", AREA_REQUIRED, DATE, "물류"),
            _c("비고", OPTIONAL, TEXT),
        ),
        references=(("거래ID", "수출예정거래", "거래ID"),),
        date_order=(("출발예정일", "도착예정일"), ("출발실제일", "도착실제일")),
    ),
    Sheet(
        name="거래처",
        primary_key="거래처ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("거래처ID", COMMON_REQUIRED, TEXT),
            _c("법인명", COMMON_REQUIRED, TEXT, aliases=("거래처명", "업체명")),
            _c("별칭", OPTIONAL, TEXT),
            _c("국가코드", AREA_REQUIRED, TEXT, "거래처·수출규제"),
            _c("국가명_원본", OPTIONAL, TEXT),
            _c("주소", AREA_REQUIRED, TEXT, "거래처·수출규제"),
            _c("등록번호종류", OPTIONAL, TEXT),
            _c("등록번호", AREA_REQUIRED, TEXT, "거래처"),
            _c("최종사용자관계", AREA_REQUIRED, TEXT, "수출규제"),
            _c("비고", OPTIONAL, TEXT),
        ),
    ),
    Sheet(
        name="증빙목록",
        primary_key="증빙ID",
        columns=(
            _c("기업ID", COMMON_REQUIRED, TEXT),
            _c("증빙ID", COMMON_REQUIRED, TEXT),
            _c("관련제품ID", AREA_REQUIRED, TEXT, "증빙"),
            _c("관련거래ID", OPTIONAL, TEXT),
            _c("문서종류", AREA_REQUIRED, TEXT, "증빙"),
            _c("문서번호", AREA_REQUIRED, TEXT, "증빙"),
            _c("발행일", AREA_REQUIRED, DATE, "증빙"),
            _c("만료일", OPTIONAL, DATE),
            _c("발행기관", OPTIONAL, TEXT),
            _c("첨부참조", OPTIONAL, TEXT),
            _c("비고", OPTIONAL, TEXT),
        ),
        references=(
            ("관련제품ID", "제품정보", "제품ID"),
            ("관련거래ID", "수출예정거래", "거래ID"),
        ),
        date_order=(("발행일", "만료일"),),
    ),
)

SHEET_BY_NAME = {s.name: s for s in SHEETS}
SHEET_NAMES = tuple(s.name for s in SHEETS)


def sheet(name: str) -> Sheet | None:
    return SHEET_BY_NAME.get(name)
