"""Demo-only monitoring analyzer interface. No camera pixels are analyzed."""
from dataclasses import dataclass

@dataclass
class ReviewCue:
    category: str
    severity: str
    description: str
    source: str = "demo"

class DemoAnalyzer:
    def analyze_metadata(self, signal: str) -> ReviewCue:
        return ReviewCue(
            category="demo_check",
            severity="low",
            description=f"Simulated check ({signal}). This is demo data, not an AI finding.",
            source="demo",
        )

analyzer = DemoAnalyzer()
