package com.sysadmindoc.viptrack;

import java.io.UnsupportedEncodingException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLEncoder;
import java.util.Locale;

/** Pure URL policy shared by the Android activity and local JVM tests. */
public final class VipTrackNavigation {
    public static final String PUBLIC_START_URL = "https://sysadmindoc.github.io/VIPTrack/index.html";
    public static final String APP_HOST = "sysadmindoc.github.io";
    public static final String APP_SCOPE_PATH = "/VIPTrack/";
    public static final String ASSET_START_URL = PUBLIC_START_URL;

    private static final String PUBLIC_PATH = "/VIPTrack/index.html";
    private static final int MAX_QUERY_LENGTH = 8_192;

    private VipTrackNavigation() {
    }

    public static boolean isInternalAssetUrl(String rawUrl) {
        URI uri = parse(rawUrl);
        if (uri == null) return false;
        String path = uri.getPath() == null ? "" : uri.getPath();
        return "https".equals(lower(uri.getScheme()))
                && APP_HOST.equals(lower(uri.getHost()))
                && uri.getUserInfo() == null
                && validHttpsPort(uri.getPort())
                && (path.isEmpty()
                    || "/".equals(path)
                    || "/VIPTrack".equals(path)
                    || path.startsWith(APP_SCOPE_PATH));
    }

    public static boolean isHostedAppUrl(String rawUrl) {
        URI uri = parse(rawUrl);
        if (uri == null) return false;
        String path = uri.getPath() == null ? "" : uri.getPath();
        boolean startPath = path.equals("/VIPTrack")
                || path.equals("/VIPTrack/")
                || path.equals(PUBLIC_PATH);
        return "https".equals(lower(uri.getScheme()))
                && APP_HOST.equals(lower(uri.getHost()))
                && uri.getUserInfo() == null
                && validHttpsPort(uri.getPort())
                && startPath;
    }

    public static boolean isSafeExternalUrl(String rawUrl) {
        URI uri = parse(rawUrl);
        if (uri == null || uri.getUserInfo() != null) return false;
        String scheme = lower(uri.getScheme());
        if ("https".equals(scheme)) {
            return uri.getHost() != null && validHttpsPort(uri.getPort());
        }
        if ("mailto".equals(scheme) || "tel".equals(scheme) || "geo".equals(scheme)) {
            return rawUrl.length() <= 2_048;
        }
        return false;
    }

    public static String toAssetUrl(String rawUrl) {
        URI uri = parse(rawUrl);
        if (uri == null || rawUrl.length() > 16_384) return ASSET_START_URL;

        boolean supported = isHostedAppUrl(rawUrl);
        if (!supported) return ASSET_START_URL;

        String query = boundedQuery(uri.getRawQuery());
        String fragment = boundedFragment(uri.getRawFragment());
        return ASSET_START_URL
                + (query.isEmpty() ? "" : "?" + query)
                + (fragment.isEmpty() ? "" : "#" + fragment);
    }

    public static String buildAssetShareUrl(String title, String text, String url) {
        StringBuilder query = new StringBuilder();
        appendQuery(query, "title", truncate(title, 200));
        appendQuery(query, "text", truncate(text, 2_000));
        appendQuery(query, "url", truncate(url, 2_000));
        return ASSET_START_URL + (query.length() == 0 ? "" : "?" + query);
    }

    public static String truncate(String value, int maxLength) {
        if (value == null || maxLength <= 0) return "";
        String normalized = value.trim();
        return normalized.length() <= maxLength ? normalized : normalized.substring(0, maxLength);
    }

    private static void appendQuery(StringBuilder query, String key, String value) {
        if (value.isEmpty()) return;
        if (query.length() > 0) query.append('&');
        query.append(key).append('=').append(urlEncode(value));
    }

    private static String urlEncode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (UnsupportedEncodingException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String boundedQuery(String query) {
        if (query == null || query.isEmpty() || query.length() > MAX_QUERY_LENGTH) return "";
        return query;
    }

    private static String boundedFragment(String fragment) {
        if (fragment == null || fragment.isEmpty() || fragment.length() > 256) return "";
        return fragment;
    }

    private static boolean validHttpsPort(int port) {
        return port == -1 || port == 443;
    }

    private static String lower(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private static URI parse(String rawUrl) {
        if (rawUrl == null || rawUrl.trim().isEmpty()) return null;
        try {
            return new URI(rawUrl.trim());
        } catch (URISyntaxException ignored) {
            return null;
        }
    }
}
