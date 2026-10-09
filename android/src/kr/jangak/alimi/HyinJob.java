package kr.jangak.alimi;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebView;

/** 하루 한 번, 앱을 열지 않아도 포털 장학캘린더를 다시 읽는다 (필요하면 저장된 아이디로 자동 로그인). */
public class HyinJob extends JobService {
    static final int ID = 7102;
    private WebView web;

    static void schedule(Context ctx) {
        JobScheduler js = (JobScheduler) ctx.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (js == null) return;
        for (JobInfo j : js.getAllPendingJobs()) if (j.getId() == ID) return;
        js.schedule(new JobInfo.Builder(ID, new ComponentName(ctx, HyinJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(24L * 60 * 60 * 1000)
                .setPersisted(true)
                .build());
    }

    @Override
    public boolean onStartJob(final JobParameters params) {
        boolean has = HyinClient.file(this).exists() || "on".equals(Cred.state(this));
        if (!has || System.currentTimeMillis() - HyinClient.file(this).lastModified() < 20L * 60 * 60 * 1000) return false;
        final Handler h = new Handler(Looper.getMainLooper());
        try {
            web = new WebView(getApplicationContext());
        } catch (Exception e) {
            return false;
        }
        final Runnable end = new Runnable() { @Override public void run() {
            if (web != null) { try { web.removeJavascriptInterface("HyinBridge"); web.destroy(); } catch (Exception ignored) { } web = null; }
            jobFinished(params, false);
        } };
        new HyinClient(this, web, true, new HyinClient.Listener() {
            @Override public void onProgress(String t) { }
            @Override public void onDone(int n) { getSharedPreferences("hyin", MODE_PRIVATE).edit().putString("state", "ok").apply(); h.post(end); }
            @Override public void onFail(String t) { getSharedPreferences("hyin", MODE_PRIVATE).edit().putString("state", "fail").apply(); h.post(end); }
            @Override public void onLoginNeeded() {
                getSharedPreferences("hyin", MODE_PRIVATE).edit().putString("state", "login").apply();
                if ("failed".equals(Cred.state(HyinJob.this))) notifyLogin();
                h.post(end);
            }
        }).start();
        h.postDelayed(new Runnable() { @Override public void run() { if (web != null) end.run(); } }, 4 * 60 * 1000);
        return true;
    }

    private void notifyLogin() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(new NotificationChannel("portal", "포털 장학캘린더", NotificationManager.IMPORTANCE_LOW));
        PendingIntent pi = PendingIntent.getActivity(this, 3, new Intent(this, PortalActivity.class), PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, "portal") : new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle("포털 자동 로그인을 멈췄어요")
                .setContentText("2차 인증이 필요하거나 비밀번호가 바뀌었을 수 있어요. 눌러서 한 번 로그인해 주세요.")
                .setStyle(new Notification.BigTextStyle().bigText("2차 인증이 필요하거나 비밀번호가 바뀌었을 수 있어요. 눌러서 한 번 로그인해 주세요."))
                .setAutoCancel(true).setContentIntent(pi);
        nm.notify(7102, b.build());
    }

    @Override public boolean onStopJob(JobParameters params) { return true; }
}
