from sqlalchemy import Boolean, Column, Integer, JSON, String, Text

from app.models.base import Base


class OPCUASource(Base):
    """Persisted OPC UA data-source configuration.

    Survives backend restarts so that configured sources/mappings are
    reloaded automatically (restart recovery). Node mappings are stored as a
    JSON array of {node_id, alias, unit, category}.
    """

    __tablename__ = "opcua_source"

    name = Column(String(255), nullable=False, default="OPC UA Source")
    endpoint_url = Column(String(512), nullable=False)
    namespace_index = Column(Integer, nullable=False, default=2)
    sampling_interval_ms = Column(Integer, nullable=False, default=1000)
    session_timeout_ms = Column(Integer, nullable=False, default=60000)

    security_mode = Column(String(32), nullable=False, default="anonymous")
    security_policy = Column(String(128), nullable=True)
    security_mode_level = Column(String(64), nullable=True)
    username = Column(String(255), nullable=True)
    # NOTE: secret material is stored as provided. In production these columns
    # should be encrypted at rest (e.g. pgcrypto / KMS-managed key).
    password = Column(Text, nullable=True)
    ca_cert_pem = Column(Text, nullable=True)
    client_cert_pem = Column(Text, nullable=True)
    client_key_pem = Column(Text, nullable=True)

    timestamp_source = Column(String(32), nullable=False, default="server")
    deduplication_enabled = Column(Boolean, nullable=False, default=True)
    unit_override_policy = Column(String(32), nullable=False, default="preserve")

    db_type = Column(String(32), nullable=False, default="timescale")
    db_name = Column(String(128), nullable=True)
    tags = Column(JSON, nullable=True)
    retention_policy = Column(String(64), nullable=True)
    store_and_forward_enabled = Column(Boolean, nullable=False, default=True)

    nodes = Column(JSON, nullable=False, default=list)
    active = Column(Boolean, nullable=False, default=False)
