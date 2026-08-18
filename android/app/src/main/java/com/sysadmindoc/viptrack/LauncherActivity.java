package com.sysadmindoc.viptrack;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ServiceWorkerClient;
import android.webkit.ServiceWorkerController;
import android.webkit.ServiceWorkerWebSettings;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import androidx.webkit.WebViewAssetLoader;

import java.lang.ref.WeakReference;

/**
 * First-party Android host for VIPTrack's mockup-derived mobile workspace.
 *
 * <p>The UI shell and small reference files are packaged in the APK and served through a secure
 * virtual HTTPS origin. Live aircraft, map tiles, and the large reference datasets stay on the
 * network, keeping the release artifact compact while preserving the browser app's local-first
 * state model.</p>
 */
public final class LauncherActivity extends Activity {
    private static final String LOG_TAG = "VIPTrack";
    private static final int LOCATION_PERMISSION_REQUEST = 4101;
    private static final int FILE_CHOOSER_REQUEST = 4102;
    private static final int NOTIFICATION_PERMISSION_REQUEST = 4103;
    private static final String ALERT_CHANNEL_ID = "viptrack-alerts";
    private static final long STARTUP_TIMEOUT_MS = 45_000L;

    private static final int COLOR_NAVY = Color.rgb(3, 16, 29);
    private static final int COLOR_NAVY_DEEP = Color.rgb(1, 8, 17);
    private static final int COLOR_PANEL = Color.rgb(10, 26, 43);
    private static final int COLOR_BORDER = Color.rgb(40, 70, 102);
    private static final int COLOR_TEAL = Color.rgb(33, 212, 180);
    private static final int COLOR_TEXT = Color.rgb(248, 250, 252);
    private static final int COLOR_MUTED = Color.rgb(159, 176, 200);

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable startupTimeout = this::handleStartupTimeout;

    private WebView webView;
    private WebViewAssetLoader assetLoader;
    private ProgressBar pageProgress;
    private FrameLayout launchOverlay;
    private TextView overlayTitle;
    private TextView overlayMessage;
    private View overlayStatusRow;
    private Button retryButton;
    private ValueCallback<Uri[]> fileChooserCallback;
    private GeolocationPermissions.Callback geolocationCallback;
    private String geolocationOrigin;
    private boolean pageReady;
    private boolean mainFrameFailed;

    private void handleStartupTimeout() {
        if (!pageReady && !isFinishing() && !isDestroyed()) {
            showFailure(getString(R.string.offline_message));
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        assetLoader = new WebViewAssetLoader.Builder()
                .setDomain(VipTrackNavigation.APP_HOST)
                .addPathHandler(VipTrackNavigation.APP_SCOPE_PATH,
                        new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        setContentView(createContentView());
        configureSystemBars();
        configureWebView();
        configureServiceWorkerRouting();

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            loadIntent(getIntent());
        } else {
            showLoading();
        }
    }

    private void configureSystemBars() {
        getWindow().setStatusBarColor(COLOR_NAVY_DEEP);
        getWindow().setNavigationBarColor(COLOR_NAVY_DEEP);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            getWindow().setNavigationBarDividerColor(COLOR_NAVY_DEEP);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                controller.setSystemBarsAppearance(
                        0,
                        WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                                | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                );
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    private View createContentView() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(COLOR_NAVY_DEEP);

        webView = new WebView(this);
        webView.setBackgroundColor(COLOR_NAVY_DEEP);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setVerticalScrollBarEnabled(false);
        webView.setContentDescription(getString(R.string.app_name));
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        pageProgress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        pageProgress.setMax(100);
        pageProgress.setProgressTintList(ColorStateList.valueOf(COLOR_TEAL));
        pageProgress.setProgressBackgroundTintList(ColorStateList.valueOf(Color.TRANSPARENT));
        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(2),
                Gravity.TOP
        );
        root.addView(pageProgress, progressParams);

        launchOverlay = createLaunchOverlay();
        root.addView(launchOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));
        return root;
    }

    private FrameLayout createLaunchOverlay() {
        FrameLayout overlay = new FrameLayout(this);
        GradientDrawable background = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{COLOR_NAVY_DEEP, COLOR_NAVY, Color.rgb(4, 24, 39)}
        );
        overlay.setBackground(background);
        overlay.setClickable(true);
        overlay.setFocusable(true);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.CENTER_HORIZONTAL);
        card.setPadding(dp(28), dp(28), dp(28), dp(26));
        GradientDrawable cardBackground = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Color.rgb(12, 31, 50), COLOR_PANEL}
        );
        cardBackground.setCornerRadius(dp(24));
        cardBackground.setStroke(dp(1), COLOR_BORDER);
        card.setBackground(cardBackground);

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.mipmap.ic_launcher);
        logo.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        logo.setContentDescription(null);
        LinearLayout.LayoutParams logoParams = new LinearLayout.LayoutParams(dp(86), dp(86));
        logoParams.bottomMargin = dp(18);
        card.addView(logo, logoParams);

        overlayTitle = textView(getString(R.string.launch_title), 30, COLOR_TEXT, Typeface.BOLD);
        overlayTitle.setLetterSpacing(-0.02f);
        card.addView(overlayTitle, wrapCentered(dp(4)));

        overlayMessage = textView(getString(R.string.launch_subtitle), 15, COLOR_MUTED, Typeface.NORMAL);
        overlayMessage.setGravity(Gravity.CENTER);
        card.addView(overlayMessage, wrapCentered(dp(22)));

        LinearLayout statusRow = new LinearLayout(this);
        statusRow.setOrientation(LinearLayout.HORIZONTAL);
        statusRow.setGravity(Gravity.CENTER);
        ProgressBar spinner = new ProgressBar(this, null, android.R.attr.progressBarStyleSmall);
        spinner.setIndeterminateTintList(ColorStateList.valueOf(COLOR_TEAL));
        statusRow.addView(spinner, new LinearLayout.LayoutParams(dp(22), dp(22)));
        TextView statusText = textView(getString(R.string.launch_status), 13, COLOR_TEAL, Typeface.BOLD);
        LinearLayout.LayoutParams statusTextParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        statusTextParams.leftMargin = dp(10);
        statusRow.addView(statusText, statusTextParams);
        overlayStatusRow = statusRow;
        card.addView(statusRow, wrapCentered(dp(2)));

        retryButton = new Button(this);
        retryButton.setText(R.string.retry);
        retryButton.setTextColor(COLOR_NAVY_DEEP);
        retryButton.setTextSize(15);
        retryButton.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        retryButton.setAllCaps(false);
        retryButton.setMinHeight(0);
        retryButton.setMinWidth(0);
        retryButton.setPadding(dp(30), dp(12), dp(30), dp(12));
        retryButton.setBackground(pillButtonBackground());
        retryButton.setVisibility(View.GONE);
        retryButton.setOnClickListener(view -> {
            showLoading();
            webView.reload();
        });
        card.addView(retryButton, wrapCentered(0));

        int displayWidth = getResources().getDisplayMetrics().widthPixels;
        FrameLayout.LayoutParams cardParams = new FrameLayout.LayoutParams(
                Math.min(dp(420), displayWidth - dp(48)),
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER
        );
        cardParams.leftMargin = dp(24);
        cardParams.rightMargin = dp(24);
        overlay.addView(card, cardParams);
        return overlay;
    }

    private LinearLayout.LayoutParams wrapCentered(int bottomMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.gravity = Gravity.CENTER_HORIZONTAL;
        params.bottomMargin = bottomMargin;
        return params;
    }

    private TextView textView(String value, int sizeSp, int color, int style) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setTypeface(Typeface.DEFAULT, style);
        return view;
    }

    private RippleDrawable pillButtonBackground() {
        GradientDrawable content = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{Color.rgb(23, 177, 158), Color.rgb(48, 231, 192)}
        );
        content.setCornerRadius(dp(18));
        GradientDrawable mask = new GradientDrawable();
        mask.setColor(Color.WHITE);
        mask.setCornerRadius(dp(18));
        return new RippleDrawable(ColorStateList.valueOf(Color.argb(80, 255, 255, 255)), content, mask);
    }

    @SuppressLint({"SetJavaScriptEnabled", "JavascriptInterface"})
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setGeolocationEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setTextZoom(100);
        settings.setDefaultTextEncodingName("UTF-8");
        settings.setUserAgentString(settings.getUserAgentString()
                + " VIPTrackAndroid/" + BuildConfig.VERSION_NAME);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, false);

        boolean debuggable = (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
        WebView.setWebContentsDebuggingEnabled(debuggable);

        webView.addJavascriptInterface(new AndroidBridge(this), "VIPTrackAndroid");
        webView.setWebViewClient(new VipTrackWebViewClient());
        webView.setWebChromeClient(new VipTrackWebChromeClient());
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (VipTrackNavigation.isSafeExternalUrl(url)) {
                openExternalUrl(url);
            }
        });
    }

    private void configureServiceWorkerRouting() {
        try {
            ServiceWorkerController controller = ServiceWorkerController.getInstance();
            ServiceWorkerWebSettings settings = controller.getServiceWorkerWebSettings();
            settings.setAllowContentAccess(false);
            settings.setAllowFileAccess(false);
            settings.setBlockNetworkLoads(false);
            settings.setCacheMode(WebSettings.LOAD_DEFAULT);
            controller.setServiceWorkerClient(new ServiceWorkerClient() {
                @Override
                public WebResourceResponse shouldInterceptRequest(WebResourceRequest request) {
                    return assetLoader.shouldInterceptRequest(request.getUrl());
                }
            });
        } catch (IllegalStateException ignored) {
            // A WebView provider without service-worker support still runs the bundled shell.
        }
    }

    private void loadIntent(Intent intent) {
        showLoading();
        webView.loadUrl(resolveIntentUrl(intent));
    }

    private String resolveIntentUrl(Intent intent) {
        if (intent == null) return VipTrackNavigation.ASSET_START_URL;

        if (Intent.ACTION_SEND.equals(intent.getAction())
                && intent.getType() != null
                && intent.getType().startsWith("text/")) {
            return VipTrackNavigation.buildAssetShareUrl(
                    intent.getStringExtra(Intent.EXTRA_SUBJECT),
                    intent.getStringExtra(Intent.EXTRA_TEXT),
                    intent.getStringExtra(Intent.EXTRA_TITLE)
            );
        }

        if (Intent.ACTION_VIEW.equals(intent.getAction()) && intent.getData() != null) {
            return VipTrackNavigation.toAssetUrl(intent.getDataString());
        }
        return VipTrackNavigation.ASSET_START_URL;
    }

    private void showLoading() {
        pageReady = false;
        mainFrameFailed = false;
        mainHandler.removeCallbacks(startupTimeout);
        mainHandler.postDelayed(startupTimeout, STARTUP_TIMEOUT_MS);
        overlayTitle.setText(R.string.launch_title);
        overlayMessage.setText(R.string.launch_subtitle);
        overlayStatusRow.setVisibility(View.VISIBLE);
        retryButton.setVisibility(View.GONE);
        launchOverlay.animate().cancel();
        launchOverlay.setAlpha(1f);
        launchOverlay.setVisibility(View.VISIBLE);
        pageProgress.setVisibility(View.VISIBLE);
        pageProgress.setProgress(6);
    }

    private void showFailure(String detail) {
        pageReady = false;
        mainFrameFailed = true;
        mainHandler.removeCallbacks(startupTimeout);
        overlayTitle.setText(R.string.offline_title);
        overlayMessage.setText(detail == null || detail.trim().isEmpty()
                ? getString(R.string.offline_message)
                : detail);
        overlayStatusRow.setVisibility(View.GONE);
        retryButton.setVisibility(View.VISIBLE);
        launchOverlay.animate().cancel();
        launchOverlay.setAlpha(1f);
        launchOverlay.setVisibility(View.VISIBLE);
        pageProgress.setVisibility(View.GONE);
    }

    private void onWebAppReady() {
        if (isFinishing() || isDestroyed()) return;
        Log.i(LOG_TAG, "Web workspace ready");
        pageReady = true;
        mainFrameFailed = false;
        mainHandler.removeCallbacks(startupTimeout);
        pageProgress.setVisibility(View.GONE);
        launchOverlay.animate()
                .alpha(0f)
                .setDuration(220L)
                .withEndAction(() -> {
                    if (pageReady) launchOverlay.setVisibility(View.GONE);
                })
                .start();
    }

    private void requestLocationPermission(String origin, GeolocationPermissions.Callback callback) {
        if (!VipTrackNavigation.isInternalAssetUrl(origin)) {
            callback.invoke(origin, false, false);
            return;
        }

        // The web app asks for a starting position during bootstrap. Defer the Android permission
        // prompt until the user explicitly taps a location feature after the workspace is ready.
        if (!pageReady) {
            callback.invoke(origin, false, false);
            return;
        }

        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            callback.invoke(origin, true, false);
            return;
        }

        if (geolocationCallback != null) {
            geolocationCallback.invoke(geolocationOrigin, false, false);
        }
        geolocationCallback = callback;
        geolocationOrigin = origin;
        requestPermissions(new String[]{
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
        }, LOCATION_PERMISSION_REQUEST);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == NOTIFICATION_PERMISSION_REQUEST) {
            // Nothing to replay: the next alert posts normally once permission is held.
            return;
        }
        if (requestCode != LOCATION_PERMISSION_REQUEST || geolocationCallback == null) return;
        boolean granted = false;
        for (int result : grantResults) {
            granted |= result == PackageManager.PERMISSION_GRANTED;
        }
        geolocationCallback.invoke(geolocationOrigin, granted, false);
        geolocationCallback = null;
        geolocationOrigin = null;
    }

    /**
     * WebView ships no Web Notifications API, so `new Notification(...)` in the page is a
     * no-op inside the app. The web layer calls through the bridge instead and we post a
     * real one here. The runtime permission is requested on first use rather than at
     * launch, matching how location is handled above.
     */
    private void postAlertNotification(String title, String body, String hex) {
        if (title == null || title.isEmpty()) return;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},
                    NOTIFICATION_PERMISSION_REQUEST);
            return;
        }

        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) return;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && manager.getNotificationChannel(ALERT_CHANNEL_ID) == null) {
            NotificationChannel channel = new NotificationChannel(
                    ALERT_CHANNEL_ID,
                    getString(R.string.alert_channel_name),
                    NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription(getString(R.string.alert_channel_description));
            manager.createNotificationChannel(channel);
        }

        // Reopening the app deep-links straight to the aircraft that fired the alert.
        Intent intent = new Intent(this, LauncherActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (hex != null && !hex.isEmpty()) intent.putExtra("viptrack_hex", hex);
        PendingIntent pending = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, ALERT_CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(title)
                .setContentText(body == null ? "" : body)
                .setAutoCancel(true)
                .setContentIntent(pending);

        // One notification per aircraft, so repeated alerts replace rather than stack.
        int id = hex == null || hex.isEmpty() ? 1 : hex.hashCode();
        manager.notify(id, builder.build());
    }

    private void openExternalUrl(String rawUrl) {
        if (!VipTrackNavigation.isSafeExternalUrl(rawUrl)) return;
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(rawUrl));
            startActivity(intent);
        } catch (ActivityNotFoundException ignored) {
            // No compatible external handler is installed.
        }
    }

    private void shareText(String title, String text, String url) {
        String safeTitle = VipTrackNavigation.truncate(title, 120);
        String safeText = VipTrackNavigation.truncate(text, 1_600);
        String safeUrl = VipTrackNavigation.isHostedAppUrl(url) ? url : VipTrackNavigation.PUBLIC_START_URL;
        StringBuilder payload = new StringBuilder();
        if (!safeText.isEmpty()) payload.append(safeText);
        if (!safeUrl.isEmpty()) {
            if (payload.length() > 0) payload.append('\n');
            payload.append(safeUrl);
        }

        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("text/plain");
        send.putExtra(Intent.EXTRA_SUBJECT, safeTitle.isEmpty() ? getString(R.string.app_name) : safeTitle);
        send.putExtra(Intent.EXTRA_TEXT, payload.toString());
        try {
            startActivity(Intent.createChooser(send, getString(R.string.share_with)));
        } catch (ActivityNotFoundException ignored) {
            // Sharing is optional when no compatible activity is installed.
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadIntent(intent);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
            webView.resumeTimers();
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.onPause();
            webView.pauseTimers();
        }
        super.onPause();
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER_REQUEST || fileChooserCallback == null) return;
        Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
        fileChooserCallback.onReceiveValue(result);
        fileChooserCallback = null;
    }

    @Override
    protected void onDestroy() {
        mainHandler.removeCallbacksAndMessages(null);
        if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
        if (geolocationCallback != null) {
            geolocationCallback.invoke(geolocationOrigin, false, false);
        }
        if (webView != null) {
            ViewGroup parent = (ViewGroup) webView.getParent();
            if (parent != null) parent.removeView(webView);
            webView.removeJavascriptInterface("VIPTrackAndroid");
            webView.stopLoading();
            webView.loadUrl("about:blank");
            webView.clearHistory();
            webView.removeAllViews();
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private final class VipTrackWebViewClient extends WebViewClient {
        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            return assetLoader.shouldInterceptRequest(request.getUrl());
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            if (!request.isForMainFrame()) return false;
            String url = request.getUrl().toString();
            if (VipTrackNavigation.isInternalAssetUrl(url)) return false;
            if (VipTrackNavigation.isSafeExternalUrl(url)) {
                openExternalUrl(url);
            }
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            super.onPageStarted(view, url, favicon);
            if (VipTrackNavigation.isInternalAssetUrl(url)) showLoading();
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            super.onPageFinished(view, url);
            if (!mainFrameFailed) pageProgress.setProgress(92);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            super.onReceivedError(view, request, error);
            if (request.isForMainFrame()) {
                showFailure(getString(R.string.offline_message));
            }
        }

        @Override
        public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
            super.onReceivedHttpError(view, request, errorResponse);
            if (request.isForMainFrame()) {
                showFailure(getString(R.string.offline_message));
            }
        }

    }

    private final class VipTrackWebChromeClient extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            if (pageReady) return;
            pageProgress.setProgress(Math.max(6, Math.min(94, newProgress)));
        }

        @Override
        public void onGeolocationPermissionsShowPrompt(
                String origin,
                GeolocationPermissions.Callback callback
        ) {
            requestLocationPermission(origin, callback);
        }

        @Override
        public void onPermissionRequest(PermissionRequest request) {
            request.deny();
        }

        @Override
        public boolean onShowFileChooser(
                WebView webView,
                ValueCallback<Uri[]> filePathCallback,
                FileChooserParams fileChooserParams
        ) {
            if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
            fileChooserCallback = filePathCallback;
            Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            picker.addCategory(Intent.CATEGORY_OPENABLE);
            picker.setType("application/json");
            picker.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/json", "text/plain", "text/csv"});
            try {
                startActivityForResult(picker, FILE_CHOOSER_REQUEST);
                return true;
            } catch (ActivityNotFoundException ignored) {
                fileChooserCallback = null;
                return false;
            }
        }
    }

    private static final class AndroidBridge {
        private final WeakReference<LauncherActivity> activityReference;

        AndroidBridge(LauncherActivity activity) {
            activityReference = new WeakReference<>(activity);
        }

        @JavascriptInterface
        public void appReady() {
            LauncherActivity activity = activityReference.get();
            if (activity != null) activity.runOnUiThread(activity::onWebAppReady);
        }

        @JavascriptInterface
        public void shareText(String title, String text, String url) {
            LauncherActivity activity = activityReference.get();
            if (activity != null) {
                activity.runOnUiThread(() -> activity.shareText(title, text, url));
            }
        }

        @JavascriptInterface
        public void notifyAlert(String title, String body, String hex) {
            LauncherActivity activity = activityReference.get();
            if (activity != null) {
                activity.runOnUiThread(() -> activity.postAlertNotification(title, body, hex));
            }
        }

        @JavascriptInterface
        public String versionName() {
            return BuildConfig.VERSION_NAME;
        }

        @JavascriptInterface
        public boolean isDebugBuild() {
            return BuildConfig.DEBUG;
        }
    }
}
