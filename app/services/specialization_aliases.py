"""Bilingual and common-name aliases for imported DTU specializations."""

SPECIALIZATION_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "computer-science-and-engineering": {
        "artificial-intelligence-and-algorithms": (
            "kunstig intelligens og algoritmer",
            "ai og algoritmer",
            "ai algoritmer",
        ),
        "cybersecurity": (
            "cybersikkerhed",
            "cyber security",
        ),
        "digital-systems": ("digitale systemer",),
        "embedded-and-distributed-systems": (
            "indlejrede og distribuerede systemer",
            "embedded og distribuerede systemer",
        ),
        "safe-and-secure-by-design": (
            "sikkerhed gennem design",
            "safe and secure design",
        ),
        "software-engineering": ("softwareudvikling",),
    },
}
