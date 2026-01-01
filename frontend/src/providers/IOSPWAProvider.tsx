/**
 * iOS PWA Provider
 * 
 * Provides comprehensive iOS PWA support including:
 * - Standalone mode detection (Dynamic Island, notch, home indicator)
 * - Safe area insets via CSS custom properties
 * - Scroll/overscroll behavior management
 * - Viewport height fixes for iOS Safari
 * - Screen wake lock (when supported)
 */
import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

interface IOSPWAContextType {
    isIOS: boolean
    isPWA: boolean
    isIOSPWA: boolean
    isStandalone: boolean
    hasDynamicIsland: boolean
    hasNotch: boolean
    safeAreaInsets: {
        top: number
        right: number
        bottom: number
        left: number
    }
}

const IOSPWAContext = createContext<IOSPWAContextType>({
    isIOS: false,
    isPWA: false,
    isIOSPWA: false,
    isStandalone: false,
    hasDynamicIsland: false,
    hasNotch: false,
    safeAreaInsets: { top: 0, right: 0, bottom: 0, left: 0 },
})

export function useIOSPWA() {
    return useContext(IOSPWAContext)
}

interface IOSPWAProviderProps {
    children: ReactNode
}

export function IOSPWAProvider({ children }: IOSPWAProviderProps) {
    const [state, setState] = useState<IOSPWAContextType>({
        isIOS: false,
        isPWA: false,
        isIOSPWA: false,
        isStandalone: false,
        hasDynamicIsland: false,
        hasNotch: false,
        safeAreaInsets: { top: 0, right: 0, bottom: 0, left: 0 },
    })

    useEffect(() => {
        // Detect iOS
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream

        // Detect standalone/PWA mode
        const isStandalone = window.matchMedia('(display-mode: standalone)').matches
            || (window.navigator as any).standalone === true

        const isPWA = isStandalone

        const isIOSPWA = isIOS && isPWA

        // Detect Dynamic Island (iPhone 14 Pro and later) or Notch
        // Dynamic Island devices have ~59px safe area, notch has ~47px, others ~20px or less
        const hasDynamicIsland = isIOS && window.screen.height >= 852 && window.devicePixelRatio >= 3
        const hasNotch = isIOS && !hasDynamicIsland && (
            window.screen.height >= 812 || // iPhone X and later
            (window.screen.width >= 375 && window.screen.height >= 812)
        )

        // Set CSS custom properties for safe areas
        const root = document.documentElement

        // Set iOS-specific body classes
        if (isIOS) {
            document.body.classList.add('ios')
        }
        if (isPWA) {
            document.body.classList.add('pwa', 'standalone')
        }
        if (isIOSPWA) {
            document.body.classList.add('ios-pwa')
        }
        if (hasDynamicIsland) {
            document.body.classList.add('has-dynamic-island')
        }
        if (hasNotch) {
            document.body.classList.add('has-notch')
        }

        // Read actual safe area insets from CSS env()
        const getSafeAreaInset = (side: string): number => {
            const temp = document.createElement('div')
            temp.style.cssText = `position: fixed; ${side}: env(safe-area-inset-${side}, 0px); visibility: hidden;`
            document.body.appendChild(temp)
            const value = parseFloat(getComputedStyle(temp)[side as any]) || 0
            document.body.removeChild(temp)
            return value
        }

        // Small delay to ensure viewport is settled
        setTimeout(() => {
            const safeAreaInsets = {
                top: getSafeAreaInset('top'),
                right: getSafeAreaInset('right'),
                bottom: getSafeAreaInset('bottom'),
                left: getSafeAreaInset('left'),
            }

            // Set custom properties
            root.style.setProperty('--safe-area-top', `${safeAreaInsets.top}px`)
            root.style.setProperty('--safe-area-right', `${safeAreaInsets.right}px`)
            root.style.setProperty('--safe-area-bottom', `${safeAreaInsets.bottom}px`)
            root.style.setProperty('--safe-area-left', `${safeAreaInsets.left}px`)

            setState({
                isIOS,
                isPWA,
                isIOSPWA,
                isStandalone,
                hasDynamicIsland,
                hasNotch,
                safeAreaInsets,
            })
        }, 100)

        // iOS viewport height fix (100vh issue)
        const updateViewportHeight = () => {
            const viewportHeight = window.visualViewport?.height ?? window.innerHeight
            const vh = viewportHeight * 0.01
            root.style.setProperty('--vh', `${vh}px`)
            root.style.setProperty('--app-height', `${viewportHeight}px`)
        }

        updateViewportHeight()
        const visualViewport = window.visualViewport
        window.addEventListener('resize', updateViewportHeight)
        window.addEventListener('orientationchange', updateViewportHeight)
        if (visualViewport) {
            visualViewport.addEventListener('resize', updateViewportHeight)
            visualViewport.addEventListener('scroll', updateViewportHeight)
        }

        // Prevent pull-to-refresh and bounce scrolling on iOS PWA
        if (isIOSPWA) {
            document.body.style.overscrollBehavior = 'none'
            document.body.style.overflow = 'hidden'
            document.body.style.position = 'fixed'
            document.body.style.width = '100%'
            document.body.style.height = '100%'

            // Allow scrolling in scroll containers only
            const preventBounce = (e: TouchEvent) => {
                const target = e.target as HTMLElement
                const scrollable = target.closest('.scroll-container, [data-scroll], .overflow-auto, .overflow-y-auto')
                if (!scrollable) {
                    e.preventDefault()
                }
            }

            document.addEventListener('touchmove', preventBounce, { passive: false })

            return () => {
                window.removeEventListener('resize', updateViewportHeight)
                window.removeEventListener('orientationchange', updateViewportHeight)
                if (visualViewport) {
                    visualViewport.removeEventListener('resize', updateViewportHeight)
                    visualViewport.removeEventListener('scroll', updateViewportHeight)
                }
                document.removeEventListener('touchmove', preventBounce)
            }
        }

        return () => {
            window.removeEventListener('resize', updateViewportHeight)
            window.removeEventListener('orientationchange', updateViewportHeight)
            if (visualViewport) {
                visualViewport.removeEventListener('resize', updateViewportHeight)
                visualViewport.removeEventListener('scroll', updateViewportHeight)
            }
        }
    }, [])

    return (
        <IOSPWAContext.Provider value={state}>
            {children}
        </IOSPWAContext.Provider>
    )
}
