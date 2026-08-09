package com.sysadmindoc.viptrack;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class VipTrackNavigationTest {
    @Test
    public void hostedAppLinksOpenTheBundledWorkspace() {
        assertEquals(
                VipTrackNavigation.ASSET_START_URL + "?hex=ae1234&panel=list#aircraft",
                VipTrackNavigation.toAssetUrl(
                        "https://sysadmindoc.github.io/VIPTrack/index.html?hex=ae1234&panel=list#aircraft"
                )
        );
        assertEquals(
                VipTrackNavigation.ASSET_START_URL,
                VipTrackNavigation.toAssetUrl("https://sysadmindoc.github.io/VIPTrack/")
        );
    }

    @Test
    public void untrustedLaunchUrlsFallBackToTheBundledStartPage() {
        assertEquals(
                VipTrackNavigation.ASSET_START_URL,
                VipTrackNavigation.toAssetUrl("https://example.com/VIPTrack/index.html?hex=ffffff")
        );
        assertEquals(
                VipTrackNavigation.ASSET_START_URL,
                VipTrackNavigation.toAssetUrl("javascript:alert(1)")
        );
        assertFalse(VipTrackNavigation.isHostedAppUrl("https://sysadmindoc.github.io.evil.test/VIPTrack/"));
        assertFalse(VipTrackNavigation.isInternalAssetUrl("http://sysadmindoc.github.io/VIPTrack/index.html"));
        assertFalse(VipTrackNavigation.isInternalAssetUrl("https://sysadmindoc.github.io.evil.test/VIPTrack/index.html"));
    }

    @Test
    public void shareIntentValuesAreBoundedAndEncoded() {
        String result = VipTrackNavigation.buildAssetShareUrl(
                "Track RCH 419",
                "RCH 419 & AE1234",
                "https://example.test/flight?id=1"
        );
        assertTrue(result.startsWith(VipTrackNavigation.ASSET_START_URL + "?"));
        assertTrue(result.contains("title=Track+RCH+419"));
        assertTrue(result.contains("text=RCH+419+%26+AE1234"));
        assertTrue(result.contains("url=https%3A%2F%2Fexample.test%2Fflight%3Fid%3D1"));
    }

    @Test
    public void onlyExplicitExternalSchemesAreOpenable() {
        assertTrue(VipTrackNavigation.isSafeExternalUrl("https://aviationweather.gov/"));
        assertTrue(VipTrackNavigation.isSafeExternalUrl("mailto:ops@example.test"));
        assertTrue(VipTrackNavigation.isSafeExternalUrl("geo:40.7,-74.0"));
        assertFalse(VipTrackNavigation.isSafeExternalUrl("http://example.test/"));
        assertFalse(VipTrackNavigation.isSafeExternalUrl("file:///sdcard/private.txt"));
        assertFalse(VipTrackNavigation.isSafeExternalUrl("intent://scan/#Intent;scheme=zxing;end"));
    }
}
