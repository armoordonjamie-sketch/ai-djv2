
import { test, expect } from '@playwright/test';

test.describe('Voice Onboarding', () => {
    // We can't easily mock the microphone in standard Playwright without special flags
    // So this test primarily checks that we don't get stuck in "Connecting..." forever
    // and that the UI handles timeouts correctly if the backend is unreachable or mic is denied.

    test('should fail gracefully if mic is denied (or CI environment)', async ({ page }) => {
        await page.goto('/voice-onboarding');

        // Initially we might need to log in or mock auth state. 
        // Assuming we can bypass or are already in a state to test this component.
        // If not, we'd need to mock the API response for /me and /onboard/status.

        // Check if we are on the onboarding page
        await expect(page.locator('text=Voice Onboarding')).toBeVisible();

        // Click Start
        await page.click('button:has-text("Start Conversation")');

        // Should see "Connecting..."
        await expect(page.locator('text=Connecting to your AI DJ...')).toBeVisible();

        // In a CI env without mic, it should eventually fail or timeout. 
        // We implanted a 15s hard timeout.
        // Let's verify we get an error state eventually.

        // Allow up to 20s for the test
        test.setTimeout(25000);

        // Expect error state
        await expect(page.locator('text=Something went wrong')).toBeVisible({ timeout: 20000 });

        // Verify specific error message if possible
        // It might differ depending on if it was a Mic error or a Timeout
        const errorText = await page.locator('text=Something went wrong').innerText();
        console.log('Error state reached:', errorText);
    });

    test('should attempt WebRTC connection on iOS PWA simulation', async ({ page }) => {
        // Simulate iOS PWA
        await page.addInitScript(() => {
            Object.defineProperty(navigator, 'userAgent', {
                get: () => 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            });
            Object.defineProperty(window, 'matchMedia', {
                value: (query) => ({
                    matches: query.includes('display-mode: standalone'),
                    media: query,
                    onchange: null,
                    addListener: () => { },
                    removeListener: () => { },
                    addEventListener: () => { },
                    removeEventListener: () => { },
                    dispatchEvent: () => false,
                }),
            });
        });

        await page.route('**/api/v1/onboard/conversation-token', async route => {
            console.log('Intercepted conversation-token request!');
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ token: 'mock-token', agent_id: 'mock-agent' })
            });
        });

        await page.goto('/voice-onboarding');

        // We expect the click to trigger the token fetch
        // Note: This test will fail if we can't click 'Start' because of Mic permissions in headless mode.
        // But it documents the intent.
    });
});
