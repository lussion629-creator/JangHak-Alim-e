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
import android.content.SharedPreferences;
import android.os.Build;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** 앱을 열지 않아도 몇 시간마다 한양대 근로 모집 새 글을 확인해 알림을 띄운다. */
public class WorkJob extends JobService {
    static final int ID = 7101;

    static void schedule(Context ctx) {
        JobScheduler js = (JobScheduler) ctx.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (js == null) return;
        for (JobInfo j : js.getAllPendingJobs()) if (j.getId() == ID) return;
        js.schedule(new JobInfo.Builder(ID, new ComponentName(ctx, WorkJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(4L * 60 * 60 * 1000)
                .setPersisted(true)
                .build());
    }

    @Override
    public boolean onStartJob(final JobParameters params) {
        new Thread(new Runnable() {
            @Override public void run() {
                try { check(WorkJob.this); } catch (Exception ignored) { }
                try { Alerts.check(WorkJob.this); } catch (Exception ignored) { }
                jobFinished(params, false);
            }
        }).start();
        return true;
    }

    @Override public boolean onStopJob(JobParameters params) { return true; }

    static void check(Context ctx) throws Exception {
        List<String[]> posts = HyWork.workPosts();
        SharedPreferences sp = ctx.getSharedPreferences("hywork", MODE_PRIVATE);
        Set<String> seen = new HashSet<>(sp.getStringSet("seen", new HashSet<String>()));
        boolean first = seen.isEmpty();
        int shown = 0;
        NotificationManager nm = (NotificationManager) ctx.getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(new NotificationChannel("work", "근로장학 모집 알림", NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent pi = PendingIntent.getActivity(ctx, 1, new Intent(ctx, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        for (String[] p : posts) {
            if (seen.add(p[0]) && !first && shown < 3) {
                Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(ctx, "work") : new Notification.Builder(ctx);
                b.setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle("새 근로장학 모집").setContentText(p[1])
                        .setStyle(new Notification.BigTextStyle().bigText(p[1])).setAutoCancel(true).setContentIntent(pi);
                nm.notify(p[0].hashCode(), b.build());
                shown++;
            }
        }
        sp.edit().putStringSet("seen", seen).apply();
    }
}
