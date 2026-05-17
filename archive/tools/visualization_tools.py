import json
import os
import pathlib
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse

from agno.tools.toolkit import Toolkit
from agno.utils.log import log_info, logger
from sqlalchemy import Column, DateTime, LargeBinary, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")


class _Base(DeclarativeBase):
    pass


class _Chart(_Base):
    __tablename__ = "charts"

    id = Column(String(36), primary_key=True)
    chart_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    image_data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VisualizationTools(Toolkit):
    def __init__(
        self,
        db_url: str,
        base_url: str = "http://localhost:7777",
        output_dir: Optional[pathlib.Path] = None,
        enable_create_bar_chart: bool = True,
        enable_create_line_chart: bool = True,
        enable_create_pie_chart: bool = True,
        enable_create_scatter_plot: bool = True,
        enable_create_histogram: bool = True,
        enable_save_chart_image: bool = True,
        all: bool = False,
        **kwargs,
    ):
        try:
            import matplotlib

            matplotlib.use("Agg")
        except ImportError as exc:
            raise ImportError(
                "matplotlib is not installed. Install with: uv add matplotlib"
            ) from exc

        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        parsed = urlparse(db_url)
        if parsed.scheme == "sqlite" and db_url != "sqlite:///:memory:":
            if db_url.startswith("sqlite:////"):
                db_path = pathlib.Path(unquote(parsed.path))
            elif db_url.startswith("sqlite:///"):
                db_path = pathlib.Path(unquote(db_url.removeprefix("sqlite:///")))
            else:
                db_path = pathlib.Path(unquote(parsed.path))
            if str(db_path) not in ("", ":memory:"):
                db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        _Base.metadata.create_all(self._engine)

        tools: List[Any] = []
        if enable_create_bar_chart or all:
            tools.append(self.create_bar_chart)
        if enable_create_line_chart or all:
            tools.append(self.create_line_chart)
        if enable_create_pie_chart or all:
            tools.append(self.create_pie_chart)
        if enable_create_scatter_plot or all:
            tools.append(self.create_scatter_plot)
        if enable_create_histogram or all:
            tools.append(self.create_histogram)
        if enable_save_chart_image or all:
            tools.append(self.save_chart_image)

        super().__init__(name="visualization_tools", tools=tools, **kwargs)

    def _apply_style(self):
        import matplotlib.pyplot as plt

        try:
            plt.style.use("seaborn-v0_8")
        except OSError:
            plt.style.use("ggplot")

    def _render_to_png(self, fig) -> bytes:
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        png_bytes = buf.read()
        buf.close()
        return png_bytes

    def _save_chart(self, png_bytes: bytes, chart_type: str, title: str) -> str:
        chart_id = str(uuid.uuid4())
        chart = _Chart(
            id=chart_id,
            chart_type=chart_type,
            title=title,
            image_data=png_bytes,
        )
        with Session(self._engine) as session:
            session.add(chart)
            session.commit()
        return chart_id

    def _get_chart_url(self, chart_id: str) -> str:
        return f"{self.base_url}/api/charts/{chart_id}"

    def get_chart_bytes(self, chart_id: str) -> Optional[bytes]:
        """Retrieve chart PNG bytes by ID. Returns None if not found."""
        try:
            with Session(self._engine) as session:
                chart = session.get(_Chart, chart_id)
                if chart:
                    return bytes(chart.image_data)
                logger.warning(f"Chart {chart_id} not found in database")
                return None
        except Exception as exc:
            logger.error(f"Error retrieving chart {chart_id}: {exc}")
            return None

    def _normalize_data_for_charts(
        self, data: Union[Dict[str, Any], List[Dict[str, Any]], List[Any], str]
    ) -> Dict[str, Union[int, float]]:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return {"Data": 1.0}

        if isinstance(data, dict):
            return {
                str(k): float(v) if isinstance(v, (int, float)) else 0
                for k, v in data.items()
            }

        if isinstance(data, list) and data:
            if isinstance(data[0], dict):
                result = {}
                for item in data:
                    if isinstance(item, dict):
                        keys = list(item.keys())
                        if len(keys) >= 2:
                            label_key = keys[0]
                            value_key = keys[1]
                            result[str(item[label_key])] = (
                                float(item[value_key])
                                if isinstance(item[value_key], (int, float))
                                else 0
                            )
                return result
            return {
                f"Item {idx + 1}": float(v) if isinstance(v, (int, float)) else 0
                for idx, v in enumerate(data)
            }

        return {"Data": 1.0}

    def _chart_response(
        self, chart_type: str, title: str, chart_id: str, data_points: int, **extra
    ) -> str:
        return json.dumps(
            {
                "chart_type": chart_type,
                "title": title,
                "chart_id": chart_id,
                "chart_url": self._get_chart_url(chart_id),
                "data_points": data_points,
                "status": "success",
                **extra,
            }
        )

    def create_bar_chart(
        self,
        data: Union[Dict[str, Union[int, float]], List[Dict[str, Any]], str],
        title: str = "Bar Chart",
        x_label: str = "Categories",
        y_label: str = "Values",
    ) -> str:
        """Create a bar chart, store it as a PNG blob, and return its chart URL."""
        try:
            import matplotlib.pyplot as plt

            normalized_data = self._normalize_data_for_charts(data)
            categories = list(normalized_data.keys())
            values = list(normalized_data.values())

            self._apply_style()
            fig = plt.figure(figsize=(10, 6))
            plt.bar(categories, values)
            plt.title(title)
            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            png_bytes = self._render_to_png(fig)
            plt.close(fig)

            chart_id = self._save_chart(png_bytes, "bar_chart", title)
            log_info(f"Bar chart created: {self._get_chart_url(chart_id)}")
            return self._chart_response("bar_chart", title, chart_id, len(normalized_data))
        except Exception as exc:
            logger.error(f"Error creating bar chart: {exc}")
            return json.dumps({"chart_type": "bar_chart", "error": str(exc), "status": "error"})

    def create_line_chart(
        self,
        data: Union[Dict[str, Union[int, float]], List[Dict[str, Any]], str],
        title: str = "Line Chart",
        x_label: str = "X-axis",
        y_label: str = "Y-axis",
    ) -> str:
        """Create a line chart, store it as a PNG blob, and return its chart URL."""
        try:
            import matplotlib.pyplot as plt

            normalized_data = self._normalize_data_for_charts(data)
            x_values = list(normalized_data.keys())
            y_values = list(normalized_data.values())

            self._apply_style()
            fig = plt.figure(figsize=(10, 6))
            plt.plot(x_values, y_values, marker="o", linewidth=2, markersize=6)
            plt.title(title)
            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.xticks(rotation=45, ha="right")
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            png_bytes = self._render_to_png(fig)
            plt.close(fig)

            chart_id = self._save_chart(png_bytes, "line_chart", title)
            log_info(f"Line chart created: {self._get_chart_url(chart_id)}")
            return self._chart_response("line_chart", title, chart_id, len(normalized_data))
        except Exception as exc:
            logger.error(f"Error creating line chart: {exc}")
            return json.dumps({"chart_type": "line_chart", "error": str(exc), "status": "error"})

    def create_pie_chart(
        self,
        data: Union[Dict[str, Union[int, float]], List[Dict[str, Any]], str],
        title: str = "Pie Chart",
    ) -> str:
        """Create a pie chart, store it as a PNG blob, and return its chart URL."""
        try:
            import matplotlib.pyplot as plt

            normalized_data = self._normalize_data_for_charts(data)
            labels = list(normalized_data.keys())
            values = list(normalized_data.values())

            self._apply_style()
            fig = plt.figure(figsize=(10, 8))
            plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
            plt.title(title)
            plt.axis("equal")

            png_bytes = self._render_to_png(fig)
            plt.close(fig)

            chart_id = self._save_chart(png_bytes, "pie_chart", title)
            log_info(f"Pie chart created: {self._get_chart_url(chart_id)}")
            return self._chart_response("pie_chart", title, chart_id, len(normalized_data))
        except Exception as exc:
            logger.error(f"Error creating pie chart: {exc}")
            return json.dumps({"chart_type": "pie_chart", "error": str(exc), "status": "error"})

    def create_scatter_plot(
        self,
        x_data: Optional[List[Union[int, float]]] = None,
        y_data: Optional[List[Union[int, float]]] = None,
        title: str = "Scatter Plot",
        x_label: str = "X-axis",
        y_label: str = "Y-axis",
        x: Optional[List[Union[int, float]]] = None,
        y: Optional[List[Union[int, float]]] = None,
        data: Optional[Union[List[List[Union[int, float]]], Dict[str, List[Union[int, float]]]]] = None,
    ) -> str:
        """Create a scatter plot, store it as a PNG blob, and return its chart URL."""
        try:
            import matplotlib.pyplot as plt

            if x_data is None:
                x_data = x
            if y_data is None:
                y_data = y
            if data is not None:
                if isinstance(data, dict) and "x" in data and "y" in data:
                    x_data = data["x"]
                    y_data = data["y"]
                elif isinstance(data, list) and data and isinstance(data[0], list) and len(data[0]) == 2:
                    x_data = [point[0] for point in data]
                    y_data = [point[1] for point in data]
            if x_data is None or y_data is None:
                raise ValueError("Missing x_data and y_data parameters")
            if len(x_data) != len(y_data):
                raise ValueError("x_data and y_data must have the same length")

            self._apply_style()
            fig = plt.figure(figsize=(10, 6))
            plt.scatter(x_data, y_data, alpha=0.7, s=50)
            plt.title(title)
            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            png_bytes = self._render_to_png(fig)
            plt.close(fig)

            chart_id = self._save_chart(png_bytes, "scatter_plot", title)
            log_info(f"Scatter plot created: {self._get_chart_url(chart_id)}")
            return self._chart_response("scatter_plot", title, chart_id, len(x_data))
        except Exception as exc:
            logger.error(f"Error creating scatter plot: {exc}")
            return json.dumps({"chart_type": "scatter_plot", "error": str(exc), "status": "error"})

    def create_histogram(
        self,
        data: List[Union[int, float]],
        bins: int = 10,
        title: str = "Histogram",
        x_label: str = "Values",
        y_label: str = "Frequency",
    ) -> str:
        """Create a histogram, store it as a PNG blob, and return its chart URL."""
        try:
            import matplotlib.pyplot as plt

            if not isinstance(data, list) or not data:
                raise ValueError("Data must be a non-empty list of numbers")
            numeric_data = []
            for value in data:
                try:
                    numeric_data.append(float(value))
                except (ValueError, TypeError):
                    continue
            if not numeric_data:
                raise ValueError("No valid numeric data found")

            self._apply_style()
            fig = plt.figure(figsize=(10, 6))
            plt.hist(numeric_data, bins=bins, alpha=0.7, edgecolor="black")
            plt.title(title)
            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            png_bytes = self._render_to_png(fig)
            plt.close(fig)

            chart_id = self._save_chart(png_bytes, "histogram", title)
            log_info(f"Histogram created: {self._get_chart_url(chart_id)}")
            return self._chart_response(
                "histogram", title, chart_id, len(numeric_data), bins=bins
            )
        except Exception as exc:
            logger.error(f"Error creating histogram: {exc}")
            return json.dumps({"chart_type": "histogram", "error": str(exc), "status": "error"})

    def save_chart_image(self, chart_id: str, path: str) -> str:
        """Save a stored chart PNG to a local file path, usually under assets/."""
        try:
            if not self.output_dir:
                raise ValueError("VisualizationTools output_dir is not configured")
            png_bytes = self.get_chart_bytes(chart_id)
            if png_bytes is None:
                raise ValueError(f"Chart not found: {chart_id}")
            target = (self.output_dir / path).resolve()
            target.relative_to(self.output_dir.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png_bytes)
            return json.dumps(
                {
                    "chart_id": chart_id,
                    "path": str(target),
                    "status": "success",
                }
            )
        except Exception as exc:
            return json.dumps({"chart_id": chart_id, "error": str(exc), "status": "error"})
