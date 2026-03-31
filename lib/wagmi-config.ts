import { http, createConfig } from 'wagmi'
import { arbitrum, mainnet } from 'wagmi/chains'
import { coinbaseWallet, walletConnect } from 'wagmi/connectors'

// Hyperliquid runs on Arbitrum
const WALLETCONNECT_PROJECT_ID = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || ''

export const config = createConfig({
  chains: [arbitrum, mainnet],
  // MetaMask auto-discovered via EIP-6963 (multiInjectedProviderDiscovery defaults to true)
  connectors: [
    coinbaseWallet({ appName: 'AIFred Trading' }),
    ...(WALLETCONNECT_PROJECT_ID
      ? [walletConnect({ projectId: WALLETCONNECT_PROJECT_ID })]
      : []),
  ],
  transports: {
    [arbitrum.id]: http(),
    [mainnet.id]: http(),
  },
})

declare module 'wagmi' {
  interface Register {
    config: typeof config
  }
}
