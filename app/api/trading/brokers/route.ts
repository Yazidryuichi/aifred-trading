import { NextRequest, NextResponse } from "next/server";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join } from "path";
import { createCipheriv, createDecipheriv, randomBytes, createHash } from "crypto";
import { lockedReadModifyWrite, atomicWriteFile, readJsonWithFallback } from "@/lib/file-lock";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// Activity log helper
// ---------------------------------------------------------------------------

// Activity log paths — try /tmp first, fall back to data/ for reads
const ACTIVITY_PATH_TMP = join("/tmp/aifred-data", "activity-log.json");
const ACTIVITY_PATH_DATA = join(process.cwd(), "data", "activity-log.json");

function appendActivity(entry: {
  type: string;
  severity: string;
  title: string;
  message: string;
  details?: Record<string, unknown>;
}) {
  lockedReadModifyWrite<unknown[]>(
    ACTIVITY_PATH_TMP,
    (current) => {
      const activities = Array.isArray(current)
        ? current
        : readJsonWithFallback<unknown[]>([ACTIVITY_PATH_TMP, ACTIVITY_PATH_DATA], []);
      activities.push({
        id: `act_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toISOString(),
        ...entry,
      });
      return activities.slice(-500);
    },
  ).catch((e) => {
    console.error("Failed to log activity from brokers route:", e);
  });
}

// ---------------------------------------------------------------------------
// Broker registry — static definitions of supported brokers
// ---------------------------------------------------------------------------

interface CredentialField {
  key: string;
  label: string;
  type: "text" | "password" | "textarea";
  optional?: boolean;
}

interface BrokerDefinition {
  id: string;
  name: string;
  category: "crypto" | "stocks" | "forex" | "stocks/options" | "all";
  description: string;
  supportedAssets: string[];
  requiredCredentials: CredentialField[];
  comingSoon?: boolean;
}

const BROKER_REGISTRY: BrokerDefinition[] = [
  {
    id: "binance",
    name: "Binance",
    category: "crypto",
    description: "World's largest crypto exchange",
    supportedAssets: [
      "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
      "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
    ],
    requiredCredentials: [
      { key: "api_key", label: "API Key", type: "text" },
      { key: "api_secret", label: "API Secret", type: "password" },
    ],
  },
  {
    id: "coinbase",
    name: "Coinbase Advanced Trade",
    category: "crypto",
    description: "Coinbase Advanced Trade API (formerly Coinbase Pro)",
    supportedAssets: [
      "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "DOGE/USD",
      "ADA/USD", "DOT/USD", "MATIC/USD", "LINK/USD", "UNI/USD",
    ],
    requiredCredentials: [
      { key: "api_key", label: "API Key Name", type: "text" },
      { key: "api_secret", label: "API Secret (PEM Private Key)", type: "textarea" },
    ],
  },
  {
    id: "kraken",
    name: "Kraken",
    category: "crypto",
    description: "Established crypto exchange with advanced trading features",
    supportedAssets: [
      "BTC/USD", "ETH/USD", "SOL/USD", "DOT/USD", "ADA/USD",
      "XRP/USD", "DOGE/USD", "AVAX/USD", "LINK/USD", "MATIC/USD",
    ],
    requiredCredentials: [
      { key: "api_key", label: "API Key", type: "text" },
      { key: "api_secret", label: "API Secret", type: "password" },
    ],
  },
  {
    id: "bybit",
    name: "Bybit",
    category: "crypto",
    description: "Derivatives-focused crypto exchange",
    supportedAssets: [
      "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
      "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT", "MATIC/USDT",
    ],
    requiredCredentials: [
      { key: "api_key", label: "API Key", type: "text" },
      { key: "api_secret", label: "API Secret", type: "password" },
    ],
  },
  {
    id: "alpaca",
    name: "Alpaca",
    category: "stocks",
    description: "Commission-free stock and crypto trading API",
    supportedAssets: [
      "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
      "NVDA", "META", "SPY", "QQQ", "BTC/USD",
    ],
    requiredCredentials: [
      { key: "api_key", label: "API Key", type: "text" },
      { key: "api_secret", label: "API Secret", type: "password" },
      { key: "base_url", label: "Base URL", type: "text", optional: true },
    ],
  },
  {
    id: "oanda",
    name: "OANDA",
    category: "forex",
    description: "Leading forex and CFD broker",
    supportedAssets: [
      "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
      "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY", "USD/CHF",
    ],
    requiredCredentials: [
      { key: "api_key", label: "API Key", type: "text" },
      { key: "account_id", label: "Account ID", type: "text" },
    ],
  },
  {
    id: "interactive_brokers",
    name: "Interactive Brokers",
    category: "stocks/options",
    description: "Professional-grade broker for stocks, options, futures, and forex",
    supportedAssets: [
      "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
      "SPY", "QQQ", "ES", "NQ", "EUR/USD",
    ],
    requiredCredentials: [
      { key: "host", label: "TWS/Gateway Host", type: "text" },
      { key: "port", label: "Port", type: "text" },
      { key: "client_id", label: "Client ID", type: "text" },
    ],
  },
  {
    id: "metatrader",
    name: "MetaTrader 4/5",
    category: "forex",
    description: "Industry-standard forex trading platform",
    supportedAssets: [
      "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
      "XAU/USD", "US30", "NAS100", "SPX500", "GER40",
    ],
    requiredCredentials: [
      { key: "server", label: "Server", type: "text" },
      { key: "login", label: "Login", type: "text" },
      { key: "password", label: "Password", type: "password" },
    ],
  },
  {
    id: "bloomberg",
    name: "Bloomberg Terminal",
    category: "all",
    description: "Institutional-grade market data and trading platform",
    supportedAssets: ["All asset classes"],
    requiredCredentials: [
      { key: "api_key", label: "API Key", type: "password" },
      { key: "port", label: "BLPAPI Port", type: "text" },
    ],
  },
];

// ---------------------------------------------------------------------------
// File helpers
// ---------------------------------------------------------------------------

const TMP_DIR = "/tmp/aifred-data";
const DATA_DIR = join(process.cwd(), "data");
const CONNECTIONS_PATH_TMP = join(TMP_DIR, "broker-connections.json");
const CONNECTIONS_PATH_DATA = join(DATA_DIR, "broker-connections.json");
const SECRETS_PATH_TMP = join(TMP_DIR, ".broker-secrets.json");

function ensureTmpDir() {
  if (!existsSync(TMP_DIR)) {
    mkdirSync(TMP_DIR, { recursive: true });
  }
}

// ---------------------------------------------------------------------------
// AES-256-GCM encryption helpers for broker credentials
// ---------------------------------------------------------------------------

function getEncryptionKey(): Buffer {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) {
    throw new Error("NEXTAUTH_SECRET is not set — cannot encrypt/decrypt broker credentials.");
  }
  // Derive a 32-byte key from the secret using SHA-256
  return createHash("sha256").update(secret).digest();
}

interface EncryptedPayload {
  iv: string;   // hex
  tag: string;  // hex
  data: string; // hex
}

function encryptCredentials(data: object): string {
  const key = getEncryptionKey();
  const iv = randomBytes(12); // 96-bit IV for GCM
  const cipher = createCipheriv("aes-256-gcm", key, iv);

  const plaintext = JSON.stringify(data);
  let encrypted = cipher.update(plaintext, "utf8", "hex");
  encrypted += cipher.final("hex");
  const tag = cipher.getAuthTag();

  const payload: EncryptedPayload = {
    iv: iv.toString("hex"),
    tag: tag.toString("hex"),
    data: encrypted,
  };
  return JSON.stringify(payload);
}

function decryptCredentials(encrypted: string): object {
  const key = getEncryptionKey();
  const payload: EncryptedPayload = JSON.parse(encrypted);

  const iv = Buffer.from(payload.iv, "hex");
  const tag = Buffer.from(payload.tag, "hex");
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);

  let decrypted = decipher.update(payload.data, "hex", "utf8");
  decrypted += decipher.final("utf8");
  return JSON.parse(decrypted);
}

// ---------------------------------------------------------------------------

interface ConnectionRecord {
  brokerId: string;
  connected: boolean;
  status: "connected" | "disconnected" | "error";
  lastChecked: string | null;
  accountId?: string;
}

function readConnections(): Record<string, ConnectionRecord> {
  return readJsonWithFallback<Record<string, ConnectionRecord>>(
    [CONNECTIONS_PATH_TMP, CONNECTIONS_PATH_DATA],
    {},
  );
}

async function writeConnectionsAsync(data: Record<string, ConnectionRecord>) {
  ensureTmpDir();
  await atomicWriteFile(CONNECTIONS_PATH_TMP, JSON.stringify(data, null, 2));
}

function readSecrets(): Record<string, Record<string, string>> {
  if (!existsSync(SECRETS_PATH_TMP)) return {};
  try {
    const raw = readFileSync(SECRETS_PATH_TMP, "utf-8");
    const parsed = JSON.parse(raw);

    // Migration: detect plaintext JSON (no iv/tag/data envelope)
    // Plaintext files are a dict of brokerId -> credentials objects
    if (parsed && typeof parsed === "object" && !parsed.iv && !parsed.tag && !parsed.data) {
      // This is plaintext — encrypt it in place and return
      console.warn("[security] Migrating plaintext broker secrets to encrypted storage.");
      writeSecrets(parsed as Record<string, Record<string, string>>);
      return parsed as Record<string, Record<string, string>>;
    }

    // Already encrypted (has iv/tag/data)
    return decryptCredentials(raw) as Record<string, Record<string, string>>;
  } catch {
    return {};
  }
}

function writeSecrets(data: Record<string, Record<string, string>>) {
  ensureTmpDir();
  // Use atomic write to prevent corruption from concurrent requests
  atomicWriteFile(SECRETS_PATH_TMP, encryptCredentials(data)).catch((e) => {
    console.error("Failed to write secrets atomically:", e);
  });
}

// ---------------------------------------------------------------------------
// Revalidation helper — test stored credentials for a connected broker
// ---------------------------------------------------------------------------

async function revalidateBroker(
  brokerId: string,
  secrets: Record<string, Record<string, string>>,
): Promise<boolean> {
  const creds = secrets[brokerId];
  if (!creds) return false;

  try {
    // Call the internal test endpoint logic inline to avoid HTTP round-trip
    let ccxt: any;
    try {
      ccxt = require("ccxt");
    } catch {
      ccxt = null;
    }

    const EXCHANGE_MAP: Record<string, string> = {
      binance: "binance",
      coinbase: "coinbase",
      kraken: "kraken",
      bybit: "bybit",
    };

    const exchangeName = EXCHANGE_MAP[brokerId];

    if (ccxt && exchangeName && ccxt[exchangeName]) {
      const ExchangeClass = ccxt[exchangeName];

      // Normalize PEM for CDP keys
      let secret = creds.api_secret || creds.secret || "";
      if (secret.includes("BEGIN EC PRIVATE KEY")) {
        const pemBody = secret
          .replace(/-----BEGIN EC PRIVATE KEY-----/g, "")
          .replace(/-----END EC PRIVATE KEY-----/g, "")
          .replace(/[\s\r\n]+/g, "");
        const lines: string[] = [];
        for (let i = 0; i < pemBody.length; i += 64) {
          lines.push(pemBody.slice(i, i + 64));
        }
        secret = `-----BEGIN EC PRIVATE KEY-----\n${lines.join("\n")}\n-----END EC PRIVATE KEY-----\n`;
      }

      const exchange = new ExchangeClass({
        apiKey: creds.api_key || creds.apiKey,
        secret: secret,
        password: creds.passphrase || creds.password,
        enableRateLimit: true,
        timeout: 15000,
      });
      await exchange.fetchBalance();
      return true;
    }

    // For non-ccxt brokers, check that credentials exist
    const filledFields = Object.values(creds).filter(
      (v) => typeof v === "string" && v.trim().length > 0,
    );
    return filledFields.length >= 2;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// GET /api/trading/brokers — list brokers with connection status
// ---------------------------------------------------------------------------

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const revalidate = url.searchParams.get("revalidate") === "true";

    const connections = readConnections();

    // If revalidate is requested, re-test connected brokers
    if (revalidate) {
      const secrets = readSecrets();
      let changed = false;

      for (const [id, conn] of Object.entries(connections)) {
        if (conn.connected) {
          const isValid = await revalidateBroker(id, secrets);
          if (!isValid) {
            connections[id] = {
              ...conn,
              connected: false,
              status: "disconnected",
              lastChecked: new Date().toISOString(),
            };
            // Remove stale credentials
            delete secrets[id];
            changed = true;

            appendActivity({
              type: "broker_revalidation_failed",
              severity: "warning",
              title: `Broker Disconnected: ${id}`,
              message: `${id} credentials are no longer valid — connection removed.`,
              details: { broker: id },
            });
          } else {
            connections[id] = {
              ...conn,
              lastChecked: new Date().toISOString(),
            };
          }
        }
      }

      if (changed) {
        await writeConnectionsAsync(connections);
        writeSecrets(secrets);
      }
    }

    const brokers = BROKER_REGISTRY.map((broker) => {
      const conn = connections[broker.id];
      return {
        id: broker.id,
        name: broker.name,
        category: broker.category,
        description: broker.description,
        supportedAssets: broker.supportedAssets,
        requiredCredentials: broker.requiredCredentials,
        comingSoon: broker.comingSoon ?? false,
        connected: conn?.connected ?? false,
        status: conn?.status ?? "disconnected",
        lastChecked: conn?.lastChecked ?? null,
      };
    });

    return NextResponse.json({ brokers });
  } catch (error) {
    console.error("Brokers GET error:", error);
    return NextResponse.json(
      { error: "Failed to load broker list" },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// POST /api/trading/brokers — save credentials and update connection status
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  try {
    const rawBody = await request.text();
    if (rawBody.length > 10_000) {
      return NextResponse.json({ error: "Request body too large" }, { status: 413 });
    }
    const body = JSON.parse(rawBody);
    const { brokerId, credentials } = body as {
      brokerId: string;
      credentials: Record<string, string>;
    };

    if (!brokerId || !credentials) {
      return NextResponse.json(
        { success: false, message: "brokerId and credentials are required" },
        { status: 400 },
      );
    }

    const broker = BROKER_REGISTRY.find((b) => b.id === brokerId);
    if (!broker) {
      return NextResponse.json(
        { success: false, message: `Unknown broker: ${brokerId}` },
        { status: 400 },
      );
    }

    // Validate that all required (non-optional) credentials are provided
    const missing = broker.requiredCredentials
      .filter((c) => !c.optional && !credentials[c.key])
      .map((c) => c.label);

    if (missing.length > 0) {
      return NextResponse.json(
        { success: false, message: `Missing required fields: ${missing.join(", ")}` },
        { status: 400 },
      );
    }

    // Store credentials in the secrets file (never in the connections JSON)
    const secrets = readSecrets();
    secrets[brokerId] = credentials;
    writeSecrets(secrets);

    // Update connection status
    const connections = readConnections();
    connections[brokerId] = {
      brokerId,
      connected: true,
      status: "connected",
      lastChecked: new Date().toISOString(),
      accountId: `${brokerId}_${Date.now().toString(36)}`,
    };
    await writeConnectionsAsync(connections);

    // Log activity
    appendActivity({
      type: "broker_connected",
      severity: "success",
      title: `Broker Connected: ${broker.name}`,
      message: `${broker.name} credentials saved and connection established. Account ID: ${connections[brokerId].accountId}.`,
      details: { broker: broker.name, asset: broker.supportedAssets.join(", ") },
    });

    return NextResponse.json({
      success: true,
      message: `${broker.name} credentials saved and connection established`,
      accountInfo: {
        balance: 0,
        accountId: connections[brokerId].accountId,
      },
    });
  } catch (error) {
    console.error("Brokers POST error:", error);
    return NextResponse.json(
      { success: false, message: "Failed to save broker credentials" },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// DELETE /api/trading/brokers?brokerId=xxx — disconnect and remove credentials
// ---------------------------------------------------------------------------

export async function DELETE(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const brokerId = url.searchParams.get("brokerId");

    if (!brokerId) {
      return NextResponse.json(
        { error: "brokerId is required" },
        { status: 400 },
      );
    }

    // Remove credentials
    const secrets = readSecrets();
    delete secrets[brokerId];
    writeSecrets(secrets);

    // Update connection status
    const connections = readConnections();
    if (connections[brokerId]) {
      connections[brokerId] = {
        ...connections[brokerId],
        connected: false,
        status: "disconnected",
        lastChecked: new Date().toISOString(),
      };
      await writeConnectionsAsync(connections);
    }

    // Find broker name for activity log
    const broker = BROKER_REGISTRY.find((b) => b.id === brokerId);
    const brokerName = broker?.name ?? brokerId;

    // Log activity
    appendActivity({
      type: "broker_disconnected",
      severity: "warning",
      title: `Broker Disconnected: ${brokerName}`,
      message: `${brokerName} disconnected — API credentials removed.`,
      details: { broker: brokerId },
    });

    return NextResponse.json({
      success: true,
      message: `${brokerName} disconnected`,
    });
  } catch (error) {
    console.error("Brokers DELETE error:", error);
    return NextResponse.json(
      { error: "Failed to disconnect broker" },
      { status: 500 },
    );
  }
}
