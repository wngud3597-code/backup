class ProvenanceTracker:
    ATTRIBUTION_TEXT = (
        "출처: Stack Overflow Developer Survey (Stack Exchange Inc.), "
        "Open Database License (ODbL) 1.0 적용."
    )

    SURVEY_URL_2026 = "https://survey.stackoverflow.co/2026/technology"
    METHODOLOGY_URL = "https://survey.stackoverflow.co/2026/methodology"

    @classmethod
    def get_provenance_meta(cls, source_role: str = "survey_statistics") -> dict:
        return {
            "source_name": "Stack Overflow Developer Survey 2026",
            "license": "ODbL-1.0",
            "publisher": "Stack Exchange Inc.",
            "attribution": cls.ATTRIBUTION_TEXT,
            "url": cls.SURVEY_URL_2026
            if source_role != "methodology"
            else cls.METHODOLOGY_URL,
        }
