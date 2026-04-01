"use client"

import { WagmiProvider } from 'wagmi'
import { config } from '@/lib/wagmi-config'
import { type ReactNode } from 'react'

export function Web3Provider({ children }: { children: ReactNode }) {
  return (
    <WagmiProvider config={config}>
      {children}
    </WagmiProvider>
  )
}
