// lib/credential-store.ts
// Credentials are stored as server-side env vars only.
// This module provides a client-side API to check connection status.

export interface BrokerStatus {
  id: string;
  name: string;
  connected: boolean;
}

export async function getConnectedBrokers(): Promise<BrokerStatus[]> {
  try {
    const res = await fetch("/api/trading/broker-status");
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export function isConnected(brokers: BrokerStatus[], brokerId: string): boolean {
  return brokers.some((b) => b.id === brokerId && b.connected);
}
