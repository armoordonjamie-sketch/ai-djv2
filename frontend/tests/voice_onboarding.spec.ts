import { test, expect } from '@playwright/test';

test('Voice Onboarding should timeout after 20s if connection fails', async ({ page }) => {
    // 1. Mock API to hang or fail
    await page.route('**/api/v1/onboard/start', async route => {
        // Determine if we should hang or return success
        // For timeout test, we can just never reply, or reply success but websocket never connects
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                signed_url: 'wss://fake-url',
                conversation_hint: { user_id: 'test-user', display_name: 'Test' }
            })
        });
    });

    // Mock WebSocket to never connect or to fail
    // Playwright doesn't easily intercept WebSocket creation to "hang" it, 
    // but if we give a bogus URL, it will fail fast or timeout.
    // The code uses a hard 20s timeout.

    // 2. Go to page
    await page.goto('/voice-onboarding');

    // 3. Click Start
    await page.click('button:has-text("Start Conversation")');

    // 4. Expect "Connecting..."
    await expect(page.locator('text=Connecting to your AI DJ')).toBeVisible();

    // 5. Fast forward or wait (Playwright doesn't do fake timers easily for browser integration without libs)
    // We will wait 20s + buffer
    test.setTimeout(30000);

    // 6. Expect Error UI
    // "Connection timed out" or "Something went wrong"
    await expect(page.locator('text=Something went wrong')).toBeVisible({ timeout: 21000 });
    await expect(page.locator('text=Connection timed out')).toBeVisible();
});
