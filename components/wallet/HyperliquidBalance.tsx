"use client"

import { useAccount } from 'wagmi'
import { useState, useEffect, useCallback } from 'react'

interface HLPosition {
  coin: string
  size: number
  entryPx: number
  unrealizedPnl: number
  leverage: number
}

interface HLBalance {
  equity: number
  availableBalance: number
  marginUsed: number
  positions: HLPosition[]
}

export function HyperliquidBalance() {
  const { address, isConnected } = useAccount()
  const [balance, setBalance] = useState<HLBalance | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchBalance = useCallback(async () => {
    if (!address) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('https://api.hyperliquid.xyz/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'clearinghouseState',
          user: address,
        }),
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const data = await res.json()

      if (data) {
        setBalance({
          equity: parseFloat(data.marginSummary?.accountValue || '0'),
          availableBalance: parseFloat(data.withdrawable || '0'),
          marginUsed: parseFloat(data.marginSummary?.totalMarginUsed || '0'),
          positions: (data.assetPositions || [])
            .filter((p: Record<string, Record<string, string>>) => parseFloat(p.position?.szi || '0') !== 0)
            .map((p: Record<string, Record<string, string | Record<string, string>>>) => ({
              coin: p.position.coin as string,
              size: parseFloat(p.position.szi as string),
              entryPx: parseFloat(p.position.entryPx as string),
              unrealizedPnl: parseFloat(p.position.unrealizedPnl as string),
              leverage: parseFloat(
                typeof p.position.leverage === 'object'
                  ? (p.position.leverage as Record<string, string>).value || '1'
                  : (p.position.leverage as string) || '1'
              ),
            })),
        })
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      console.error('Failed to fetch HL balance:', message)
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [address])

  useEffect(() => {
    if (!isConnected || !address) {
      setBalance(null)
      setError(null)
      return
    }

    fetchBalance()
    const interval = setInterval(fetchBalance, 15000) // refresh every 15s
    return () => clearInterval(interval)
  }, [address, isConnected, fetchBalance])

  if (!isConnected) return null

  if (loading && !balance) {
    return (
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4">
        <div className="text-xs text-zinc-500 font-medium mb-3 uppercase tracking-wider">
          Hyperliquid Account
        </div>
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <span className="w-3 h-3 border-2 border-zinc-600 border-t-zinc-400 rounded-full animate-spin" />
          Loading Hyperliquid data...
        </div>
      </div>
    )
  }

  if (error && !balance) {
    return (
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4">
        <div className="text-xs text-zinc-500 font-medium mb-3 uppercase tracking-wider">
          Hyperliquid Account
        </div>
        <div className="text-sm text-red-400">
          Failed to load: {error}
        </div>
        <button
          onClick={fetchBalance}
          className="mt-2 text-xs text-zinc-400 hover:text-white transition-colors underline"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!balance) return null

  const formatUsd = (value: number) =>
    value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4">
      <div className="text-xs text-zinc-500 font-medium mb-3 uppercase tracking-wider">
        Hyperliquid Account
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div>
          <div className="text-xs text-zinc-500">Equity</div>
          <div className="text-lg font-semibold text-white">
            ${formatUsd(balance.equity)}
          </div>
        </div>
        <div>
          <div className="text-xs text-zinc-500">Available</div>
          <div className="text-lg font-semibold text-emerald-400">
            ${formatUsd(balance.availableBalance)}
          </div>
        </div>
        <div>
          <div className="text-xs text-zinc-500">Margin Used</div>
          <div className="text-lg font-semibold text-yellow-400">
            ${formatUsd(balance.marginUsed)}
          </div>
        </div>
      </div>

      {balance.positions.length > 0 && (
        <>
          <div className="text-xs text-zinc-500 font-medium mb-2 uppercase tracking-wider">
            Open Positions
          </div>
          <div className="space-y-2">
            {balance.positions.map((pos) => (
              <div key={pos.coin} className="flex items-center justify-between p-2 bg-zinc-800/50 rounded">
                <div>
                  <span className="text-sm font-medium text-white">{pos.coin}</span>
                  <span className={`ml-2 text-xs ${pos.size > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {pos.size > 0 ? 'LONG' : 'SHORT'}
                  </span>
                  <span className="ml-2 text-xs text-zinc-500">{pos.leverage}x</span>
                </div>
                <div className="text-right">
                  <div className="text-xs text-zinc-400">
                    {Math.abs(pos.size).toFixed(4)} @ ${pos.entryPx.toFixed(2)}
                  </div>
                  <div className={`text-sm font-medium ${pos.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {pos.unrealizedPnl >= 0 ? '+' : ''}${pos.unrealizedPnl.toFixed(2)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {balance.positions.length === 0 && (
        <div className="text-sm text-zinc-600 text-center py-2">No open positions</div>
      )}
    </div>
  )
}
