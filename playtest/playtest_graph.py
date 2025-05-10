import asyncio
import io

import altair as alt
import pandas as pd

BUCKETS = {
    "Easy -": (0.0, 1.18),
    "Easy": (1.18, 1.76),
    "Easy +": (1.76, 2.35),
    "Medium -": (2.35, 2.94),
    "Medium": (2.94, 3.53),
    "Medium +": (3.53, 4.12),
    "Hard -": (4.12, 4.71),
    "Hard": (4.71, 5.29),
    "Hard +": (5.29, 5.88),
    "Very Hard -": (5.88, 6.47),
    "Very Hard": (6.47, 7.06),
    "Very Hard +": (7.06, 7.65),
    "Extreme -": (7.65, 8.24),
    "Extreme": (8.24, 8.82),
    "Extreme +": (8.82, 9.41),
    "Hell": (9.41, 10.0)
}
COLORS = {
    "Easy -": "#66ff66",
    "Easy": "#4dcc4d",
    "Easy +": "#33cc33",
    "Medium -": "#99ff33",
    "Medium": "#99e600",
    "Medium +": "#80cc00",
    "Hard -": "#ffd633",
    "Hard": "#ffb300",
    "Hard +": "#ff9900",
    "Very Hard -": "#ff8000",
    "Very Hard": "#e67e00",
    "Very Hard +": "#cc6600",
    "Extreme -": "#ff4d00",
    "Extreme": "#e04300",
    "Extreme +": "#b92d00",
    "Hell": "#990000",
}

HELL_VALUE = 10.0

class VoteHistogram:
    def __init__(self, votes: list[float]) -> None:
        self.votes = votes
        self.df_votes = pd.DataFrame({'vote': votes})
        self.avg_vote = self.df_votes['vote'].mean()

    @staticmethod
    def _find_bucket_name(val: float) -> str:
        """Return the bucket name for a given vote value (used for displaying the average)."""
        for bucket, (low, high) in BUCKETS.items():
            if low <= val < high or (bucket == "Hell" and val == HELL_VALUE):
                return bucket
        return "Unknown Difficulty"

    @staticmethod
    def _assign_bucket(val: float) -> str:
        """Assign a vote to its bucket."""
        for bucket, (low, high) in BUCKETS.items():
            if low <= val < high or (bucket == "Hell" and val == HELL_VALUE):
                return bucket
        return ""

    def _prepare_data(self) -> pd.DataFrame:
        """Assign buckets and return the votes DataFrame with bucket assignments."""
        self.df_votes['bucket'] = self.df_votes['vote'].apply(self._assign_bucket)
        return self.df_votes

    @staticmethod
    def _create_bucket_df() -> pd.DataFrame:
        """Create a DataFrame for bucket definitions ensuring every bucket is present."""
        bucket_df = pd.DataFrame([
            {"bucket": b, "color": COLORS[b]}
            for b in BUCKETS
        ])
        return bucket_df

    @staticmethod
    def _get_bucket_for_vote(val: float) -> str:
        """Map a vote value to its bucket name."""
        for bucket, (low, high) in BUCKETS.items():
            if low <= val < high or (bucket == "Hell" and val == HELL_VALUE):
                return bucket
        return "Unknown Difficulty"

    def build_chart(self) -> alt.LayerChart:
        avg_bucket = self._get_bucket_for_vote(self.avg_vote)
        avg_vote_str = self._find_bucket_name(self.avg_vote)

        background = alt.Chart(self._create_bucket_df()).mark_bar(opacity=0.2).encode(
            x=alt.X(
                "bucket:N",
                sort=list(BUCKETS.keys()),
                scale=alt.Scale(paddingInner=0, paddingOuter=0),
                axis=alt.Axis(labels=True, title=None),
            ),
            y=alt.value(0),
            y2=alt.value(150),
            color=alt.Color("color:N", scale=None),
        )

        avg_rule = alt.Chart(pd.DataFrame({"bucket": [avg_bucket]})).mark_rule(
            color="black", strokeDash=[4, 2], size=2
        ).encode(
            x=alt.X("bucket:N", sort=list(BUCKETS.keys()))
        )

        avg_circle = alt.Chart(pd.DataFrame({"bucket": [avg_bucket]})).mark_point(
            shape="circle", size=100, color="black", opacity=1, filled=True  # Full opacity and solid color
        ).encode(
            x=alt.X("bucket:N", sort=list(BUCKETS.keys()))
        )

        chart = alt.layer(background, avg_rule, avg_circle).properties(
            title=f"Playtest Votes | Average Vote = {self.avg_vote:.2f} ({avg_vote_str})",
            width=600,
            height=150,
        ).configure_axis(
            labelAngle=-45,
            labelPadding=5,
            titlePadding=0,
        ).configure_view(
            strokeWidth=0,
        )

        return chart

    async def export_png_bytes_async(self, scale_factor: float = 2.0) -> io.BytesIO:
        """Asynchronously render the chart to PNG bytes without blocking the event loop."""
        # Offload the blocking .to_image(...) call
        png_bytes = await asyncio.to_thread(self.build_chart().to_image, format="png", scale_factor=scale_factor)
        buf = io.BytesIO(png_bytes)
        buf.seek(0)
        return buf
