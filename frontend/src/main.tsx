import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, HashRouter } from 'react-router-dom'
import App from './App'
import './index.css'

// Use HashRouter for iOS PWA standalone mode (BrowserRouter breaks navigation)
const isStandalone = window.matchMedia('(display-mode: standalone)').matches
  || (window.navigator as any).standalone
const Router = isStandalone ? HashRouter : BrowserRouter

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Router>
      <App />
    </Router>
  </StrictMode>,
)
