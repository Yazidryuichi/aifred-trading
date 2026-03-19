// Client-side broker credential storage
// Credentials are obfuscated in localStorage to prevent casual reading.

const STORAGE_KEY = 'aifred_broker_credentials';
const OBFUSCATION_KEY = 'AIFr3d-Tr4d1ng-2026';

export interface StoredBrokerCredentials {
  [brokerId: string]: {
    credentials: Record<string, string>;
    connectedAt: string;
    lastTested: string;
    testResult: 'success' | 'failed';
    accountInfo?: {
      balance: Record<string, number>;
      accountId: string;
    };
  };
}

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined';
}

function obfuscate(text: string): string {
  try {
    // Use encodeURIComponent to handle all Unicode safely before btoa
    const utf8 = encodeURIComponent(text);
    const xored = Array.from(utf8).map((char, i) =>
      String.fromCharCode(char.charCodeAt(0) ^ OBFUSCATION_KEY.charCodeAt(i % OBFUSCATION_KEY.length))
    ).join('');
    return btoa(unescape(encodeURIComponent(xored)));
  } catch {
    // Fallback: just base64 encode
    return btoa(encodeURIComponent(text));
  }
}

function deobfuscate(encoded: string): string {
  try {
    const decoded = atob(encoded);
    const xored = Array.from(decoded).map((char, i) =>
      String.fromCharCode(char.charCodeAt(0) ^ OBFUSCATION_KEY.charCodeAt(i % OBFUSCATION_KEY.length))
    ).join('');
    return decodeURIComponent(xored);
  } catch {
    try {
      // Fallback: try plain base64
      return decodeURIComponent(atob(encoded));
    } catch {
      return '{}';
    }
  }
}

export function saveCredentials(
  brokerId: string,
  credentials: Record<string, string>,
  testResult: { success: boolean; balance?: Record<string, number>; accountId?: string },
) {
  if (!isBrowser()) return;
  const stored = loadAllCredentials();
  stored[brokerId] = {
    credentials,
    connectedAt: new Date().toISOString(),
    lastTested: new Date().toISOString(),
    testResult: testResult.success ? 'success' : 'failed',
    accountInfo: testResult.success ? {
      balance: testResult.balance || {},
      accountId: testResult.accountId || `${brokerId}_${Date.now().toString(36)}`,
    } : undefined,
  };
  try {
    localStorage.setItem(STORAGE_KEY, obfuscate(JSON.stringify(stored)));
  } catch { /* storage full or blocked */ }
}

export function loadAllCredentials(): StoredBrokerCredentials {
  if (!isBrowser()) return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const text = deobfuscate(raw);
    const parsed = JSON.parse(text);
    if (typeof parsed === 'object' && parsed !== null) return parsed;
    return {};
  } catch {
    return {};
  }
}

export function loadCredentials(brokerId: string): Record<string, string> | null {
  try {
    const stored = loadAllCredentials();
    return stored[brokerId]?.credentials || null;
  } catch {
    return null;
  }
}

export function removeCredentials(brokerId: string) {
  if (!isBrowser()) return;
  try {
    const stored = loadAllCredentials();
    delete stored[brokerId];
    if (Object.keys(stored).length === 0) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, obfuscate(JSON.stringify(stored)));
    }
  } catch { /* ignore */ }
}

export function isConnected(brokerId: string): boolean {
  try {
    const stored = loadAllCredentials();
    return stored[brokerId]?.testResult === 'success';
  } catch {
    return false;
  }
}

export function getConnectedBrokerIds(): string[] {
  try {
    const stored = loadAllCredentials();
    return Object.keys(stored).filter(id => stored[id]?.testResult === 'success');
  } catch {
    return [];
  }
}
