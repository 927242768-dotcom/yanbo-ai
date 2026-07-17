package com.yanbo.ai;

import android.annotation.SuppressLint;
import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;

import androidx.core.content.FileProvider;

import com.getcapacitor.BridgeActivity;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends BridgeActivity {
    private static final int UNKNOWN_SOURCES_REQUEST = 8042;
    private static final String APK_MIME = "application/vnd.android.package-archive";

    private final ExecutorService updateExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private DownloadManager downloadManager;
    private ConnectivityManager connectivityManager;
    private ConnectivityManager.NetworkCallback networkCallback;
    private long updateDownloadId = -1L;
    private Uri pendingApkUri;
    private boolean waitingForInstallPermission = false;
    private Runnable pendingOfflineNotification;

    private final BroadcastReceiver downloadReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (!DownloadManager.ACTION_DOWNLOAD_COMPLETE.equals(intent.getAction())) {
                return;
            }
            long completedId = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L);
            if (completedId != updateDownloadId || downloadManager == null) {
                return;
            }
            pendingApkUri = downloadManager.getUriForDownloadedFile(completedId);
            if (pendingApkUri == null) {
                notifyUpdate("error", 0, "更新包下载失败，请重试");
                return;
            }
            openInstallerOrPermission();
        }
    };

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        downloadManager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
        WebView webView = getBridge().getWebView();
        WebSettings webSettings = webView.getSettings();
        webSettings.setDomStorageEnabled(true);
        webSettings.setCacheMode(WebSettings.LOAD_DEFAULT);
        webSettings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            webSettings.setOffscreenPreRaster(true);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            webView.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, true);
        }
        webView.addJavascriptInterface(new AndroidUpdateBridge(), "YanboAndroid");
        registerNetworkMonitoring();

        IntentFilter filter = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(downloadReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(downloadReceiver, filter);
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        WebView webView = getBridge().getWebView();
        webView.onResume();
        notifyNetworkChanged(isNetworkAvailable());
        notifyAppStateChanged(true);
        if (waitingForInstallPermission && pendingApkUri != null && canInstallPackages()) {
            waitingForInstallPermission = false;
            launchInstaller();
        }
    }

    @Override
    public void onPause() {
        notifyAppStateChanged(false);
        super.onPause();
    }

    @Override
    public void onDestroy() {
        try {
            unregisterReceiver(downloadReceiver);
        } catch (IllegalArgumentException ignored) {
            // 接收器可能尚未注册完成。
        }
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {
                // 网络回调可能已经由系统移除。
            }
        }
        if (pendingOfflineNotification != null) {
            mainHandler.removeCallbacks(pendingOfflineNotification);
            pendingOfflineNotification = null;
        }
        updateExecutor.shutdownNow();
        super.onDestroy();
    }

    private final class AndroidUpdateBridge {
        @JavascriptInterface
        public void installUpdate(String url, String version, String expectedSha256, long expectedSize) {
            runOnUiThread(() -> beginUpdateDownload(url, version, expectedSha256, expectedSize));
        }

        @JavascriptInterface
        public boolean isNetworkAvailable() {
            return MainActivity.this.isNetworkAvailable();
        }

        @JavascriptInterface
        public String getAppVersion() {
            try {
                String version = getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
                return version == null || version.trim().isEmpty() ? "0.0.0" : version;
            } catch (Exception ignored) {
                return "0.0.0";
            }
        }
    }

    private void registerNetworkMonitoring() {
        connectivityManager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (connectivityManager == null) {
            return;
        }
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                notifyNetworkChanged(true);
            }

            @Override
            public void onLost(Network network) {
                notifyNetworkChanged(isNetworkAvailable());
            }

            @Override
            public void onCapabilitiesChanged(Network network, NetworkCapabilities capabilities) {
                notifyNetworkChanged(isNetworkAvailable());
            }
        };
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                connectivityManager.registerDefaultNetworkCallback(networkCallback);
            } else {
                NetworkRequest request = new NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .build();
                connectivityManager.registerNetworkCallback(request, networkCallback);
            }
        } catch (Exception ignored) {
            networkCallback = null;
        }
    }

    private boolean isNetworkAvailable() {
        if (connectivityManager == null) {
            connectivityManager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        }
        if (connectivityManager == null) {
            return false;
        }
        try {
            Network activeNetwork = connectivityManager.getActiveNetwork();
            NetworkCapabilities capabilities = connectivityManager.getNetworkCapabilities(activeNetwork);
            return capabilities != null
                && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
        } catch (Exception ignored) {
            return false;
        }
    }

    private void notifyNetworkChanged(boolean online) {
        runOnUiThread(() -> {
            if (pendingOfflineNotification != null) {
                mainHandler.removeCallbacks(pendingOfflineNotification);
                pendingOfflineNotification = null;
            }
            if (online) {
                applyNetworkState(true);
                return;
            }
            pendingOfflineNotification = () -> {
                pendingOfflineNotification = null;
                applyNetworkState(isNetworkAvailable());
            };
            mainHandler.postDelayed(pendingOfflineNotification, 1800L);
        });
    }

    private void applyNetworkState(boolean online) {
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebView webView = getBridge().getWebView();
        webView.setNetworkAvailable(online);
        webView.evaluateJavascript(
            "window.onYanboNetworkChanged&&window.onYanboNetworkChanged(" + online + ");",
            null
        );
    }

    private void notifyAppStateChanged(boolean active) {
        runOnUiThread(() -> {
            if (getBridge() == null || getBridge().getWebView() == null) {
                return;
            }
            getBridge().getWebView().evaluateJavascript(
                "window.onYanboAppStateChanged&&window.onYanboAppStateChanged(" + active + ");",
                null
            );
        });
    }

    private void beginUpdateDownload(String rawUrl, String rawVersion, String expectedSha256, long expectedSize) {
        if (downloadManager == null) {
            notifyUpdate("error", 0, "系统下载服务不可用");
            return;
        }

        Uri uri;
        try {
            uri = Uri.parse(rawUrl);
        } catch (Exception exception) {
            notifyUpdate("error", 0, "更新地址无效");
            return;
        }
        String scheme = uri.getScheme();
        if (scheme == null || !(scheme.equalsIgnoreCase("https") || scheme.equalsIgnoreCase("http"))) {
            notifyUpdate("error", 0, "更新地址无效");
            return;
        }

        String safeVersion = rawVersion == null ? "latest" : rawVersion.replaceAll("[^0-9A-Za-z._-]", "");
        if (safeVersion.isEmpty()) {
            safeVersion = "latest";
        }
        String fileName = "Yanbo-AI-Android-v" + safeVersion + ".apk";
        File downloadDirectory = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (downloadDirectory != null) {
            File previous = new File(downloadDirectory, fileName);
            if (previous.exists() && matchesExpectedUpdate(previous, expectedSha256, expectedSize)) {
                pendingApkUri = FileProvider.getUriForFile(
                    this,
                    getPackageName() + ".fileprovider",
                    previous
                );
                notifyUpdate("progress", 100, "已找到完整更新包，无需重复下载");
                openInstallerOrPermission();
                return;
            }
            if (previous.exists() && !previous.delete()) {
                notifyUpdate("error", 0, "无法清理旧更新包，请稍后重试");
                return;
            }
        }

        try {
            if (updateDownloadId >= 0L) {
                downloadManager.remove(updateDownloadId);
            }
            DownloadManager.Request request = new DownloadManager.Request(uri)
                .setTitle("彦博 AI 更新")
                .setDescription("正在下载版本 " + safeVersion)
                .setMimeType(APK_MIME)
                .setAllowedOverMetered(true)
                .setAllowedOverRoaming(true)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, fileName);
            pendingApkUri = null;
            waitingForInstallPermission = false;
            updateDownloadId = downloadManager.enqueue(request);
            notifyUpdate("started", 2, "开始下载彦博 AI " + safeVersion + "……");
            monitorDownload(updateDownloadId);
        } catch (Exception exception) {
            notifyUpdate("error", 0, "无法开始下载更新：" + readableMessage(exception));
        }
    }

    private void monitorDownload(long downloadId) {
        updateExecutor.execute(() -> {
            int previousPercent = -1;
            while (!Thread.currentThread().isInterrupted() && downloadId == updateDownloadId) {
                DownloadManager.Query query = new DownloadManager.Query().setFilterById(downloadId);
                try (Cursor cursor = downloadManager.query(query)) {
                    if (cursor == null || !cursor.moveToFirst()) {
                        notifyUpdate("error", 0, "无法读取更新下载状态");
                        return;
                    }
                    int status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                    long downloaded = cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                    long total = cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                    if (status == DownloadManager.STATUS_FAILED) {
                        notifyUpdate("error", 0, "更新下载失败，请检查网络后重试");
                        return;
                    }
                    if (status == DownloadManager.STATUS_SUCCESSFUL) {
                        notifyUpdate("progress", 100, "更新包下载完成");
                        return;
                    }
                    int percent = total > 0 ? (int) Math.min(99, downloaded * 100L / total) : 5;
                    if (percent != previousPercent) {
                        previousPercent = percent;
                        notifyUpdate("progress", percent, "正在下载更新 " + percent + "%");
                    }
                } catch (Exception exception) {
                    notifyUpdate("error", 0, "更新下载异常：" + readableMessage(exception));
                    return;
                }
                try {
                    Thread.sleep(450L);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        });
    }

    private boolean matchesExpectedUpdate(File file, String expectedSha256, long expectedSize) {
        if (!file.isFile() || file.length() <= 0L) {
            return false;
        }
        if (expectedSize > 0L && file.length() != expectedSize) {
            return false;
        }
        String normalizedHash = expectedSha256 == null
            ? ""
            : expectedSha256.trim().toLowerCase(Locale.ROOT);
        if (normalizedHash.isEmpty()) {
            return expectedSize > 0L;
        }
        try (FileInputStream input = new FileInputStream(file)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                if (count > 0) {
                    digest.update(buffer, 0, count);
                }
            }
            StringBuilder actual = new StringBuilder();
            for (byte value : digest.digest()) {
                actual.append(String.format(Locale.ROOT, "%02x", value & 0xff));
            }
            return normalizedHash.equals(actual.toString());
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean canInstallPackages() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getPackageManager().canRequestPackageInstalls();
    }

    private void openInstallerOrPermission() {
        if (!canInstallPackages()) {
            waitingForInstallPermission = true;
            notifyUpdate("permission", 100, "请允许彦博 AI 安装应用更新，然后返回继续");
            Intent permissionIntent = new Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + getPackageName())
            );
            startActivityForResult(permissionIntent, UNKNOWN_SOURCES_REQUEST);
            return;
        }
        launchInstaller();
    }

    private void launchInstaller() {
        if (pendingApkUri == null) {
            notifyUpdate("error", 0, "没有找到已下载的更新包");
            return;
        }
        try {
            Intent installIntent = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(pendingApkUri, APK_MIME)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            notifyUpdate("installing", 100, "下载完成，请在系统界面确认安装");
            startActivity(installIntent);
        } catch (Exception exception) {
            notifyUpdate("error", 0, "无法打开安装界面：" + readableMessage(exception));
        }
    }

    private void notifyUpdate(String status, int percent, String message) {
        JSONObject payload = new JSONObject();
        try {
            payload.put("status", status);
            payload.put("percent", percent);
            payload.put("message", message);
        } catch (Exception ignored) {
            return;
        }
        String javascript = "window.onYanboUpdateStatus&&window.onYanboUpdateStatus(" + payload + ");";
        runOnUiThread(() -> getBridge().getWebView().evaluateJavascript(javascript, null));
    }

    private static String readableMessage(Exception exception) {
        String message = exception.getMessage();
        return message == null || message.trim().isEmpty() ? "未知错误" : message;
    }
}
