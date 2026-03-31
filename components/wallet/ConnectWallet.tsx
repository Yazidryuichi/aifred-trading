"use client"

import { useAccount, useConnect, useDisconnect, useBalance } from 'wagmi'
import { arbitrum } from 'wagmi/chains'
import { formatUnits } from 'viem'
import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'

export function ConnectWallet() {
  const { address, isConnected, chain } = useAccount()
  const { connectors, connect, isPending } = useConnect()
  const { disconnect } = useDisconnect()
  const { data: balance } = useBalance({ address, chainId: arbitrum.id })
  const [showDropdown, setShowDropdown] = useState(false)
  const [connectError, setConnectError] = useState<string | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const [dropdownPos, setDropdownPos] = useState({ top: 0, right: 0 })

  // Position dropdown below button
  useEffect(() => {
    if (showDropdown && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect()
      setDropdownPos({
        top: rect.bottom + 8,
        right: window.innerWidth - rect.right,
      })
    }
  }, [showDropdown])

  // Close on click outside
  useEffect(() => {
    if (!showDropdown) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        dropdownRef.current && !dropdownRef.current.contains(target) &&
        buttonRef.current && !buttonRef.current.contains(target)
      ) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showDropdown])

  // Close on Escape
  useEffect(() => {
    if (!showDropdown) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowDropdown(false) }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [showDropdown])

  // Portal dropdown rendered in document.body (escapes header stacking context)
  const renderDropdown = (content: React.ReactNode) => {
    if (!showDropdown || typeof document === 'undefined') return null
    return createPortal(
      <div
        ref={dropdownRef}
        className="fixed w-64 bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl p-3"
        style={{
          top: dropdownPos.top,
          right: dropdownPos.right,
          zIndex: 99999,
          pointerEvents: 'auto',
        }}
      >
        {content}
      </div>,
      document.body
    )
  }

  if (isConnected && address) {
    const shortAddr = `${address.slice(0, 6)}...${address.slice(-4)}`
    return (
      <>
        <button
          ref={buttonRef}
          onClick={() => setShowDropdown(!showDropdown)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg hover:bg-emerald-500/20 transition-all"
        >
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm font-mono text-emerald-400">{shortAddr}</span>
          {chain && <span className="text-xs text-zinc-500">{chain.name}</span>}
        </button>

        {renderDropdown(
          <>
            <div className="text-xs text-zinc-500 mb-1">Connected Wallet</div>
            <div className="text-sm font-mono text-white mb-3 break-all">{address}</div>
            {balance && (
              <div className="mb-3">
                <div className="text-xs text-zinc-500">Balance (Arbitrum)</div>
                <div className="text-sm text-white">
                  {parseFloat(formatUnits(balance.value, balance.decimals)).toFixed(4)} {balance.symbol}
                </div>
              </div>
            )}
            {chain?.id !== arbitrum.id && (
              <div className="mb-3 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded text-xs text-yellow-400">
                Switch to Arbitrum for Hyperliquid trading
              </div>
            )}
            <button
              onClick={() => { disconnect(); setShowDropdown(false) }}
              className="w-full px-3 py-2 text-sm text-red-400 border border-red-500/30 rounded hover:bg-red-500/10 transition-all"
            >
              Disconnect
            </button>
          </>
        )}
      </>
    )
  }

  return (
    <>
      <button
        ref={buttonRef}
        onClick={() => setShowDropdown(!showDropdown)}
        className="px-4 py-2 bg-emerald-500 text-black font-semibold text-sm rounded-lg hover:bg-emerald-400 transition-all"
      >
        Connect Wallet
      </button>

      {renderDropdown(
        <>
          <div className="text-xs text-zinc-400 mb-2">Choose a wallet</div>
          {connectError && (
            <div className="mb-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400 break-words">
              {connectError}
            </div>
          )}
          {/* Deduplicate connectors — prefer EIP-6963 (io.metamask) over generic injected */}
          {(() => {
            const seen = new Set<string>()
            const deduped = connectors.filter((c) => {
              // Group by display name
              const key = c.name === 'MetaMask' ? 'metamask' :
                c.name === 'Coinbase Wallet' ? 'coinbase' : c.id
              if (seen.has(key)) return false
              seen.add(key)
              return true
            })
            return deduped
          })().map((connector) => {
            const isMetaMask = connector.id === 'injected' || connector.id === 'metaMask' || connector.id === 'io.metamask' || connector.name === 'MetaMask'
            const displayName = isMetaMask ? 'MetaMask' : connector.name
            const icon = isMetaMask ? 'MM' : connector.name === 'WalletConnect' ? 'WC' : connector.name.slice(0, 2).toUpperCase()
            const subtitle = isMetaMask ? 'Browser extension' :
              connector.name === 'Coinbase Wallet' ? 'Coinbase extension' :
              connector.name === 'WalletConnect' ? 'Mobile & desktop' : 'Wallet'

            return (
              <button
                key={connector.uid}
                onClick={() => {
                  setConnectError(null)
                  connect({ connector }, {
                    onSuccess: () => setShowDropdown(false),
                    onError: (err) => setConnectError(err.message ?? 'Connection failed'),
                  })
                  // Do NOT close dropdown here — closing before MetaMask popup
                  // appears causes the browser to block the popup as untrusted
                }}
                disabled={isPending}
                className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-white rounded-lg hover:bg-zinc-800 transition-all disabled:opacity-50 mb-1"
              >
                <span className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center text-xs font-bold text-zinc-400 uppercase">
                  {icon}
                </span>
                <div className="text-left">
                  <div className="font-medium">{displayName}</div>
                  <div className="text-xs text-zinc-500">{subtitle}</div>
                </div>
              </button>
            )
          })}
          {connectors.length === 0 && (
            <div className="text-sm text-zinc-500 text-center py-3">
              No wallets detected. Install MetaMask.
            </div>
          )}
        </>
      )}
    </>
  )
}
