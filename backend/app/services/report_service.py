import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Sequence

from fpdf import FPDF
from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.alarm import Alarm, ACTIVE_ALARM_STATUSES
from app.models.prediction import Prediction
from app.models.sensor_data import SensorData
from app.schemas.report import ReportRequest, ReportResponse
from typing import Any

settings = get_settings()
settings.reports_dir.mkdir(parents=True, exist_ok=True)


async def build_summary(
    session: AsyncSession,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    machine_id: Optional[str] = None,
) -> dict:
    """Aggregate a prediction summary and an alarm summary for a time window.

    Satisfies the "Prediction Summary" and "Alarm Summary" acceptance items.
    """
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=7)

    # ---- Prediction summary (counts by status) ----
    pred_stmt = select(Prediction.status, func.count(Prediction.id)).where(
        Prediction.timestamp >= start, Prediction.timestamp <= end
    )
    if machine_id:
        pred_stmt = pred_stmt.where(Prediction.machine_id == machine_id)
    pred_stmt = pred_stmt.group_by(Prediction.status)
    pred_rows = (await session.execute(pred_stmt)).all()
    pred_by_status = {str(status or "unknown"): int(count) for status, count in pred_rows}
    pred_total = sum(pred_by_status.values())

    avg_conf_stmt = select(func.avg(Prediction.confidence)).where(
        Prediction.timestamp >= start, Prediction.timestamp <= end
    )
    if machine_id:
        avg_conf_stmt = avg_conf_stmt.where(Prediction.machine_id == machine_id)
    avg_confidence = await session.scalar(avg_conf_stmt)

    # ---- Alarm summary (counts by severity + active/resolved) ----
    alarm_stmt = select(Alarm.severity, func.count(Alarm.id)).where(
        Alarm.triggered_at >= start, Alarm.triggered_at <= end
    )
    if machine_id:
        alarm_stmt = alarm_stmt.where(Alarm.machine_id == machine_id)
    alarm_stmt = alarm_stmt.group_by(Alarm.severity)
    alarm_rows = (await session.execute(alarm_stmt)).all()
    alarm_by_severity = {str(sev or "unknown"): int(count) for sev, count in alarm_rows}
    alarm_total = sum(alarm_by_severity.values())

    active_stmt = select(func.count(Alarm.id)).where(
        Alarm.triggered_at >= start,
        Alarm.triggered_at <= end,
        Alarm.status.in_(ACTIVE_ALARM_STATUSES),
    )
    if machine_id:
        active_stmt = active_stmt.where(Alarm.machine_id == machine_id)
    active_alarms = await session.scalar(active_stmt) or 0

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "machine_id": machine_id,
        "prediction_summary": {
            "total": pred_total,
            "by_status": pred_by_status,
            "average_confidence": round(float(avg_confidence), 4) if avg_confidence is not None else None,
        },
        "alarm_summary": {
            "total": alarm_total,
            "by_severity": alarm_by_severity,
            "active": int(active_alarms),
            "resolved": alarm_total - int(active_alarms),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _fetch_rows(session: AsyncSession, params: ReportRequest) -> Sequence[SensorData]:
    # Only select columns that exist in the database (exclude readings and raw_payload if they don't exist)
    stmt = select(
        SensorData.id,
        SensorData.sensor_id,
        SensorData.machine_id,
        SensorData.timestamp,
        SensorData.value,
        SensorData.status,
        SensorData.metadata_json,
        SensorData.idempotency_key,
        SensorData.created_at,
        SensorData.updated_at
    )
    filters = []
    if params.machine_id:
        filters.append(SensorData.machine_id == params.machine_id)
    if params.sensor_id:
        filters.append(SensorData.sensor_id == params.sensor_id)
    if params.date_from:
        filters.append(SensorData.timestamp >= params.date_from)
    if params.date_to:
        filters.append(SensorData.timestamp <= params.date_to)
    if filters:
        stmt = stmt.where(and_(*filters))
    # Optimize: Order by timestamp desc and limit to 5000 rows max for faster CSV generation
    stmt = stmt.order_by(SensorData.timestamp.desc()).limit(5000)
    result = await session.execute(stmt)
    # Convert to SensorData-like objects
    rows = []
    for row in result.all():
        # Create a simple object with the attributes we need
        class SensorDataRow:
            def __init__(self, row_data):
                self.id = row_data.id
                self.sensor_id = row_data.sensor_id
                self.machine_id = row_data.machine_id
                self.timestamp = row_data.timestamp
                self.value = row_data.value
                self.status = row_data.status
                self.metadata = row_data.metadata_json
        rows.append(SensorDataRow(row))
    # Reverse to chronological order for CSV
    return list(reversed(rows))


def _write_csv(rows: Sequence[SensorData], path: Path) -> None:
    fieldnames = ["timestamp", "machine_id", "sensor_id", "value", "status"]
    try:
        # Use buffered writing for better performance
        with path.open("w", newline="", encoding="utf-8", buffering=8192) as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            # Batch write for better performance
            batch_size = 100
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                for row in batch:
                    try:
                        writer.writerow(
                            {
                                "timestamp": row.timestamp.isoformat() if row.timestamp else "",
                                "machine_id": str(row.machine_id) if row.machine_id else "",
                                "sensor_id": str(row.sensor_id) if row.sensor_id else "",
                                "value": float(row.value) if row.value is not None else 0.0,
                                "status": str(row.status) if row.status else "unknown",
                            }
                        )
                    except Exception as e:
                        logger.warning("Error writing CSV row: {}", e)
                        continue
        logger.info("CSV file written successfully: {} ({} rows)", path, len(rows))
    except Exception as e:
        logger.error("Error writing CSV file: {}", e, exc_info=True)
        raise


def _write_pdf(rows: Sequence[SensorData], path: Path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Predictive Maintenance Report", ln=True)
    pdf.set_font("Arial", size=10)
    for row in rows[:200]:
        pdf.multi_cell(
            0,
            8,
            f"{row.timestamp.isoformat()} | Machine {row.machine_id} | Sensor {row.sensor_id} -> {float(row.value)} ({row.status})",
        )
    pdf.output(str(path))


async def generate_report_fast(session: AsyncSession, params: ReportRequest) -> ReportResponse:
    """Fast CSV generation optimized for speed"""
    try:
        rows = await _fetch_rows(session, params)
        logger.info("Fetched {} rows for fast CSV report", len(rows))
        
        if not rows:
            raise ValueError("No data found for the selected criteria")
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_name = f"report_{timestamp}.csv"
        report_path = settings.reports_dir / file_name

        # Ensure reports directory exists
        settings.reports_dir.mkdir(parents=True, exist_ok=True)

        # Fast CSV writing
        _write_csv(rows, report_path)

        logger.info("Fast CSV report generated at {}", report_path)
        
        if not report_path.exists():
            raise FileNotFoundError(f"Report file was not created at {report_path}")
        
        return ReportResponse(
            report_name=file_name, 
            url=f"/reports/download/{file_name}", 
            generated_at=datetime.utcnow()
        )
    except Exception as e:
        logger.error("Error generating fast CSV report: {}", e, exc_info=True)
        raise


async def generate_report(session: AsyncSession, params: ReportRequest) -> ReportResponse:
    try:
        rows = await _fetch_rows(session, params)
        logger.info("Fetched {} rows for report", len(rows))
        
        if not rows:
            logger.warning("No data found for report generation")
            # Return empty report or raise error
            raise ValueError("No data found for the selected criteria")
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_name = f"report_{timestamp}.{params.format}"
        report_path = settings.reports_dir / file_name

        # Ensure reports directory exists
        settings.reports_dir.mkdir(parents=True, exist_ok=True)

        if params.format == "pdf":
            _write_pdf(rows, report_path)
        elif params.format == "csv":
            _write_csv(rows, report_path)
        elif params.format == "xlsx":
            # For now, generate CSV for xlsx requests (can add openpyxl later)
            logger.warning("XLSX format requested, generating CSV instead")
            file_name = f"report_{timestamp}.csv"
            report_path = settings.reports_dir / file_name
            _write_csv(rows, report_path)
        else:
            # Default to CSV
            _write_csv(rows, report_path)

        logger.info("Report generated at {}", report_path)
        
        # Verify file was created
        if not report_path.exists():
            raise FileNotFoundError(f"Report file was not created at {report_path}")
        
        return ReportResponse(
            report_name=file_name, 
            url=f"/reports/download/{file_name}", 
            generated_at=datetime.utcnow()
        )
    except Exception as e:
        logger.error("Error generating report: {}", e, exc_info=True)
        raise

