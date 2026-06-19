import React, { useState } from "react";
import api from "../api";

type SecurityMode = "anonymous" | "username_password" | "certificate";

type NodeSelection = {
    nodeId: string;
    alias: string;
    unit: string;
    category: string;
};

type BasicConnectionState = {
    endpointUrl: string;
    namespaceIndex: number;
    samplingIntervalMs: number;
    sessionTimeoutMs: number;
};

type SecurityState = {
    mode: SecurityMode;
    username: string;
    password: string;
    caCertPem: string;
    clientCertPem: string;
    clientKeyPem: string;
    securityPolicy: string;
    securityModeLevel: string;
};

type PayloadState = {
    timestampSource: "server" | "client";
    deduplicationEnabled: boolean;
    unitOverridePolicy: string;
};

type RoutingState = {
    dbType: "timescale" | "influx";
    dbName: string;
    tagTenant: string;
    tagLine: string;
    tagMachine: string;
    retentionPolicy: string;
    storeAndForwardEnabled: boolean;
};

type TestResult = {
    ok: boolean;
    handshakeLogs: string[];
    samplePreview: any[];
};

const cardClass =
    "bg-slate-900/70 border border-slate-700/40 rounded-3xl p-6 shadow-2xl shadow-black/30 backdrop-blur";

export default function OPCUAWizard() {
    const [step, setStep] = useState<number>(1);

    const [basic, setBasic] = useState<BasicConnectionState>({
        endpointUrl: "opc.tcp://localhost:4840",
        namespaceIndex: 2,
        samplingIntervalMs: 1000,
        sessionTimeoutMs: 60000,
    });

    const [security, setSecurity] = useState<SecurityState>({
        mode: "anonymous",
        username: "",
        password: "",
        caCertPem: "",
        clientCertPem: "",
        clientKeyPem: "",
        securityPolicy: "Basic256Sha256",
        securityModeLevel: "SignAndEncrypt",
    });

    const [nodes, setNodes] = useState<NodeSelection[]>([
        { nodeId: "ns=2;s=Demo.Motor.Current", alias: "motor_current", unit: "A", category: "electrical" },
    ]);

    const [payloadCfg, setPayloadCfg] = useState<PayloadState>({
        timestampSource: "server",
        deduplicationEnabled: true,
        unitOverridePolicy: "preserve",
    });

    const [routing, setRouting] = useState<RoutingState>({
        dbType: "timescale",
        dbName: "pm_db",
        tagTenant: "default",
        tagLine: "line-1",
        tagMachine: "opcua-machine",
        retentionPolicy: "",
        storeAndForwardEnabled: true,
    });

    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<TestResult | null>(null);
    const [activationMessage, setActivationMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const steps = [
        "Basic Connection",
        "Security",
        "Nodes",
        "Payload & Schema",
        "Routing & DB",
        "Test + Activate",
    ];

    const buildPayload = () => {
        return {
            name: "OPC UA Source",
            endpoint_url: basic.endpointUrl,
            namespace_index: basic.namespaceIndex,
            sampling_interval_ms: basic.samplingIntervalMs,
            session_timeout_ms: basic.sessionTimeoutMs,
            security_mode: security.mode,
            security_policy: security.securityPolicy,
            security_mode_level: security.securityModeLevel,
            username: security.mode === "username_password" ? security.username : undefined,
            password: security.mode === "username_password" ? security.password : undefined,
            ca_cert_pem: security.mode === "certificate" ? security.caCertPem : undefined,
            client_cert_pem: security.mode === "certificate" ? security.clientCertPem : undefined,
            client_key_pem: security.mode === "certificate" ? security.clientKeyPem : undefined,
            timestamp_source: payloadCfg.timestampSource,
            deduplication_enabled: payloadCfg.deduplicationEnabled,
            unit_override_policy: payloadCfg.unitOverridePolicy,
            db_type: routing.dbType,
            db_name: routing.dbName,
            tags: {
                tenant: routing.tagTenant,
                line: routing.tagLine,
                machine: routing.tagMachine,
            },
            retention_policy: routing.retentionPolicy || undefined,
            store_and_forward_enabled: routing.storeAndForwardEnabled,
            nodes: nodes.map((n) => ({
                node_id: n.nodeId,
                alias: n.alias,
                unit: n.unit || undefined,
                category: n.category || undefined,
            })),
        };
    };

    const handleTest = async () => {
        try {
            setIsTesting(true);
            setError(null);
            setActivationMessage(null);
            const payload = buildPayload();
            const response = await api.post("/opcua/test", payload);
            setTestResult({
                ok: response.data.ok,
                handshakeLogs: response.data.handshake_logs || [],
                samplePreview: response.data.sample_preview || [],
            });
        } catch (err: any) {
            setError(err?.response?.data?.detail || err.message || "Test failed");
        } finally {
            setIsTesting(false);
        }
    };

    const handleActivate = async () => {
        try {
            setIsTesting(true);
            setError(null);
            const payload = buildPayload();
            const response = await api.post("/opcua/activate", payload);
            setActivationMessage(
                `Source activated (${response.data.name}) with ${response.data.node_count} node(s).`
            );
        } catch (err: any) {
            setError(err?.response?.data?.detail || err.message || "Activation failed");
        } finally {
            setIsTesting(false);
        }
    };

    const addNode = () => {
        setNodes((prev) => [
            ...prev,
            { nodeId: "", alias: "", unit: "", category: "" },
        ]);
    };

    const updateNode = (index: number, patch: Partial<NodeSelection>) => {
        setNodes((prev) => prev.map((n, i) => (i === index ? { ...n, ...patch } : n)));
    };

    const removeNode = (index: number) => {
        setNodes((prev) => prev.filter((_, i) => i !== index));
    };

    const renderStep = () => {
        switch (step) {
            case 1:
                return (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-200 mb-1">
                                Endpoint URL
                            </label>
                            <input
                                type="text"
                                className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                placeholder="opc.tcp://host:port"
                                value={basic.endpointUrl}
                                onChange={(e) =>
                                    setBasic({ ...basic, endpointUrl: e.target.value })
                                }
                            />
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    Namespace Index
                                </label>
                                <input
                                    type="number"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={basic.namespaceIndex}
                                    onChange={(e) =>
                                        setBasic({
                                            ...basic,
                                            namespaceIndex: Number(e.target.value) || 0,
                                        })
                                    }
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    Sampling Interval (ms)
                                </label>
                                <input
                                    type="number"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={basic.samplingIntervalMs}
                                    onChange={(e) =>
                                        setBasic({
                                            ...basic,
                                            samplingIntervalMs: Number(e.target.value) || 0,
                                        })
                                    }
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    Session Timeout (ms)
                                </label>
                                <input
                                    type="number"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={basic.sessionTimeoutMs}
                                    onChange={(e) =>
                                        setBasic({
                                            ...basic,
                                            sessionTimeoutMs: Number(e.target.value) || 0,
                                        })
                                    }
                                />
                            </div>
                        </div>
                    </div>
                );
            case 2:
                return (
                    <div className="space-y-4">
                        <div className="flex gap-3">
                            {(["anonymous", "username_password", "certificate"] as SecurityMode[]).map(
                                (m) => (
                                    <button
                                        key={m}
                                        type="button"
                                        onClick={() => setSecurity({ ...security, mode: m })}
                                        className={`px-3 py-1.5 rounded-full text-sm border ${
                                            security.mode === m
                                                ? "bg-emerald-500/80 border-emerald-400 text-slate-900"
                                                : "bg-slate-900/70 border-slate-700 text-slate-200"
                                        }`}
                                    >
                                        {m === "anonymous"
                                            ? "Anonymous"
                                            : m === "username_password"
                                            ? "Username + Password"
                                            : "Certificate (mTLS)"}
                                    </button>
                                )
                            )}
                        </div>
                        {security.mode === "username_password" && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-200 mb-1">
                                        Username
                                    </label>
                                    <input
                                        type="text"
                                        className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                        value={security.username}
                                        onChange={(e) =>
                                            setSecurity({ ...security, username: e.target.value })
                                        }
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-200 mb-1">
                                        Password
                                    </label>
                                    <input
                                        type="password"
                                        className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                        value={security.password}
                                        onChange={(e) =>
                                            setSecurity({ ...security, password: e.target.value })
                                        }
                                    />
                                </div>
                            </div>
                        )}
                        {security.mode === "certificate" && (
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-200 mb-1">
                                        CA Certificate (PEM)
                                    </label>
                                    <textarea
                                        className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 h-20"
                                        value={security.caCertPem}
                                        onChange={(e) =>
                                            setSecurity({ ...security, caCertPem: e.target.value })
                                        }
                                    />
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-200 mb-1">
                                            Client Certificate (PEM)
                                        </label>
                                        <textarea
                                            className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 h-24"
                                            value={security.clientCertPem}
                                            onChange={(e) =>
                                                setSecurity({
                                                    ...security,
                                                    clientCertPem: e.target.value,
                                                })
                                            }
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-200 mb-1">
                                            Client Private Key (PEM)
                                        </label>
                                        <textarea
                                            className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 h-24"
                                            value={security.clientKeyPem}
                                            onChange={(e) =>
                                                setSecurity({
                                                    ...security,
                                                    clientKeyPem: e.target.value,
                                                })
                                            }
                                        />
                                    </div>
                                </div>
                            </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    Security Policy
                                </label>
                                <input
                                    type="text"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={security.securityPolicy}
                                    onChange={(e) =>
                                        setSecurity({
                                            ...security,
                                            securityPolicy: e.target.value,
                                        })
                                    }
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    Security Mode
                                </label>
                                <input
                                    type="text"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={security.securityModeLevel}
                                    onChange={(e) =>
                                        setSecurity({
                                            ...security,
                                            securityModeLevel: e.target.value,
                                        })
                                    }
                                />
                            </div>
                        </div>
                    </div>
                );
            case 3:
                return (
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <h3 className="text-sm font-semibold text-slate-100">
                                    Node Browsing & Selection
                                </h3>
                                <p className="text-xs text-slate-400">
                                    Manually specify OPC UA node IDs. A live browser can be wired here
                                    later without changing this layout.
                                </p>
                            </div>
                            <button
                                type="button"
                                className="px-3 py-1.5 rounded-full text-sm bg-slate-800 border border-slate-600 text-slate-100 hover:bg-slate-700"
                                onClick={addNode}
                            >
                                + Add Node
                            </button>
                        </div>
                        <div className="space-y-3">
                            {nodes.map((n, i) => (
                                <div
                                    key={i}
                                    className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end bg-slate-900/60 border border-slate-700/60 rounded-2xl p-3"
                                >
                                    <div className="md:col-span-2">
                                        <label className="block text-xs font-medium text-slate-300 mb-1">
                                            Node ID
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                            value={n.nodeId}
                                            onChange={(e) =>
                                                updateNode(i, { nodeId: e.target.value })
                                            }
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-slate-300 mb-1">
                                            Alias
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                            value={n.alias}
                                            onChange={(e) =>
                                                updateNode(i, { alias: e.target.value })
                                            }
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-slate-300 mb-1">
                                            Unit
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                            value={n.unit}
                                            onChange={(e) =>
                                                updateNode(i, { unit: e.target.value })
                                            }
                                        />
                                    </div>
                                    <div className="flex gap-2">
                                        <div className="flex-1">
                                            <label className="block text-xs font-medium text-slate-300 mb-1">
                                                Category
                                            </label>
                                            <input
                                                type="text"
                                                className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                                value={n.category}
                                                onChange={(e) =>
                                                    updateNode(i, { category: e.target.value })
                                                }
                                            />
                                        </div>
                                        <button
                                            type="button"
                                            className="self-end px-2 py-1 rounded-lg text-xs bg-rose-600/80 text-slate-50 hover:bg-rose-600"
                                            onClick={() => removeNode(i)}
                                        >
                                            Remove
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                );
            case 4:
                return (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-200 mb-1">
                                Timestamp Source
                            </label>
                            <select
                                className="w-full md:w-64 rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                value={payloadCfg.timestampSource}
                                onChange={(e) =>
                                    setPayloadCfg({
                                        ...payloadCfg,
                                        timestampSource: e.target.value as "server" | "client",
                                    })
                                }
                            >
                                <option value="server">Server</option>
                                <option value="client">Client</option>
                            </select>
                        </div>
                        <div className="flex flex-wrap items-center gap-4">
                            <label className="inline-flex items-center gap-2 text-sm text-slate-100">
                                <input
                                    type="checkbox"
                                    className="rounded border-slate-600 bg-slate-900"
                                    checked={payloadCfg.deduplicationEnabled}
                                    onChange={(e) =>
                                        setPayloadCfg({
                                            ...payloadCfg,
                                            deduplicationEnabled: e.target.checked,
                                        })
                                    }
                                />
                                Deduplication enabled
                            </label>
                            <div>
                                <label className="block text-xs font-medium text-slate-300 mb-1">
                                    Unit Override Policy
                                </label>
                                <input
                                    type="text"
                                    className="w-56 rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                    value={payloadCfg.unitOverridePolicy}
                                    onChange={(e) =>
                                        setPayloadCfg({
                                            ...payloadCfg,
                                            unitOverridePolicy: e.target.value,
                                        })
                                    }
                                />
                            </div>
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-100 mb-2">
                                Payload Preview
                            </h3>
                            <pre className="bg-slate-900/80 border border-slate-700 rounded-2xl px-4 py-3 text-xs text-slate-200 overflow-x-auto">
{`{
  "timestamp": "...",
  "alias": "motor_current",
  "value": 12.3,
  "quality": "Good",
  "unit": "A"
}`}
                            </pre>
                        </div>
                    </div>
                );
            case 5:
                return (
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    DB Type
                                </label>
                                <select
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={routing.dbType}
                                    onChange={(e) =>
                                        setRouting({
                                            ...routing,
                                            dbType: e.target.value as "timescale" | "influx",
                                        })
                                    }
                                >
                                    <option value="timescale">TimescaleDB</option>
                                    <option value="influx">InfluxDB</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-200 mb-1">
                                    Bucket / DB Name
                                </label>
                                <input
                                    type="text"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-2 text-slate-100"
                                    value={routing.dbName}
                                    onChange={(e) =>
                                        setRouting({ ...routing, dbName: e.target.value })
                                    }
                                />
                            </div>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label className="block text-xs font-medium text-slate-300 mb-1">
                                    Tag: Tenant
                                </label>
                                <input
                                    type="text"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                    value={routing.tagTenant}
                                    onChange={(e) =>
                                        setRouting({ ...routing, tagTenant: e.target.value })
                                    }
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-300 mb-1">
                                    Tag: Line
                                </label>
                                <input
                                    type="text"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                    value={routing.tagLine}
                                    onChange={(e) =>
                                        setRouting({ ...routing, tagLine: e.target.value })
                                    }
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-300 mb-1">
                                    Tag: Machine
                                </label>
                                <input
                                    type="text"
                                    className="w-full rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                    value={routing.tagMachine}
                                    onChange={(e) =>
                                        setRouting({ ...routing, tagMachine: e.target.value })
                                    }
                                />
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-4">
                            <div>
                                <label className="block text-xs font-medium text-slate-300 mb-1">
                                    Retention Options
                                </label>
                                <input
                                    type="text"
                                    className="w-64 rounded-xl bg-slate-900/80 border border-slate-700 px-3 py-1.5 text-slate-100 text-sm"
                                    value={routing.retentionPolicy}
                                    onChange={(e) =>
                                        setRouting({
                                            ...routing,
                                            retentionPolicy: e.target.value,
                                        })
                                    }
                                    placeholder="e.g. 30d"
                                />
                            </div>
                            <label className="inline-flex items-center gap-2 text-sm text-slate-100">
                                <input
                                    type="checkbox"
                                    className="rounded border-slate-600 bg-slate-900"
                                    checked={routing.storeAndForwardEnabled}
                                    onChange={(e) =>
                                        setRouting({
                                            ...routing,
                                            storeAndForwardEnabled: e.target.checked,
                                        })
                                    }
                                />
                                Enable Store &amp; Forward
                            </label>
                        </div>
                    </div>
                );
            case 6:
                return (
                    <div className="space-y-4">
                        <div className="flex flex-wrap items-center gap-3">
                            <button
                                type="button"
                                onClick={handleTest}
                                disabled={isTesting}
                                className="px-4 py-2 rounded-xl bg-slate-800 border border-slate-600 text-slate-100 text-sm hover:bg-slate-700 disabled:opacity-60"
                            >
                                {isTesting ? "Testing..." : "Test Connection"}
                            </button>
                            <button
                                type="button"
                                onClick={handleActivate}
                                disabled={isTesting}
                                className="px-4 py-2 rounded-xl bg-emerald-500 text-slate-900 text-sm font-semibold hover:bg-emerald-400 disabled:opacity-60"
                            >
                                Activate Source
                            </button>
                        </div>
                        {error && (
                            <div className="rounded-xl border border-rose-500/60 bg-rose-900/40 px-3 py-2 text-xs text-rose-100">
                                {error}
                            </div>
                        )}
                        {activationMessage && (
                            <div className="rounded-xl border border-emerald-500/60 bg-emerald-900/40 px-3 py-2 text-xs text-emerald-100">
                                {activationMessage}
                            </div>
                        )}
                        {testResult && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <h3 className="text-sm font-semibold text-slate-100 mb-2">
                                        Handshake Logs
                                    </h3>
                                    <div className="bg-slate-900/80 border border-slate-700 rounded-2xl px-3 py-2 text-xs text-slate-200 h-40 overflow-y-auto space-y-1">
                                        {testResult.handshakeLogs.map((l, i) => (
                                            <div key={i}>{l}</div>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-slate-100 mb-2">
                                        Node Sample Preview
                                    </h3>
                                    <pre className="bg-slate-900/80 border border-slate-700 rounded-2xl px-3 py-2 text-xs text-slate-200 h-40 overflow-y-auto">
                                        {JSON.stringify(testResult.samplePreview, null, 2)}
                                    </pre>
                                </div>
                            </div>
                        )}
                    </div>
                );
            default:
                return null;
        }
    };

    return (
        <main className="min-h-screen bg-[#010313] text-slate-50 flex items-center justify-center px-4 py-10">
            <div className="w-full max-w-5xl">
                <div className="mb-6">
                    <h1 className="text-2xl font-semibold text-emerald-400">
                        OPC UA Source Onboarding
                    </h1>
                    <p className="text-sm text-slate-400">
                        Configure OPC UA endpoints using the same stepper-style wizard used
                        elsewhere in the platform.
                    </p>
                </div>
                <div className={cardClass}>
                    <div className="flex flex-wrap items-center gap-3 mb-6">
                        {steps.map((label, index) => {
                            const current = index + 1;
                            const active = current === step;
                            const completed = current < step;
                            return (
                                <div key={label} className="flex items-center gap-2">
                                    <div
                                        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                                            active
                                                ? "bg-emerald-500 text-slate-900"
                                                : completed
                                                ? "bg-emerald-700/80 text-emerald-50"
                                                : "bg-slate-800 text-slate-300"
                                        }`}
                                    >
                                        {current}
                                    </div>
                                    <span className="text-xs md:text-sm text-slate-200">
                                        {label}
                                    </span>
                                    {index < steps.length - 1 && (
                                        <div className="hidden md:block w-8 h-px bg-slate-700" />
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    <div className="space-y-6">
                        {renderStep()}
                        <div className="flex items-center justify-between pt-4 border-t border-slate-800 mt-4">
                            <button
                                type="button"
                                className="px-3 py-2 rounded-xl text-sm bg-slate-800 text-slate-100 border border-slate-700 disabled:opacity-50"
                                disabled={step === 1}
                                onClick={() => setStep((s) => Math.max(1, s - 1))}
                            >
                                Previous
                            </button>
                            <span className="text-xs text-slate-400 hidden md:inline">
                                Payload format is fixed:&nbsp;
                                <code className="bg-slate-900/80 border border-slate-700 rounded-md px-2 py-1">
                                    {`{ timestamp, alias, value, quality, unit }`}
                                </code>
                            </span>
                            <button
                                type="button"
                                className="px-4 py-2 rounded-xl text-sm bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400 disabled:opacity-50"
                                disabled={step === steps.length}
                                onClick={() =>
                                    setStep((s) => Math.min(steps.length, s + 1))
                                }
                            >
                                Next
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    );
}


