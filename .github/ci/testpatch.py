"""점검용 빌드에만 넣는 수정 (배포 앱에는 들어가지 않음): 셸에서 '내 학교 포털'을 정하고 화면 저장까지 자동으로 누른다."""
import re
m = "android/AndroidManifest.xml"; s = open(m, encoding="utf-8").read()
s = s.replace('<activity android:name=".PortalActivity" android:exported="false"', '<activity android:name=".PortalActivity" android:exported="true"')
s = s.replace("<application ", '<application android:debuggable="true" ', 1)
open(m, "w", encoding="utf-8").write(s)
p = "android/src/kr/jangak/alimi/PortalActivity.java"; s = open(p, encoding="utf-8").read()
s = s.replace("        super.onCreate(saved);", """        super.onCreate(saved);
        String td = getIntent().getStringExtra("t_domain");
        if (td != null) getSharedPreferences(Portal.MY, MODE_PRIVATE).edit().putString("name", "TEST").putString("domain", td).putString("entry", getIntent().getStringExtra("t_entry")).apply();""", 1)
s = s.replace("        client.start();", """        client.start();
        if (getIntent().getBooleanExtra("t_save", false)) web.postDelayed(new Runnable() { @Override public void run() { client.saveHere(); } }, 25000);""", 1)
open(p, "w", encoding="utf-8").write(s)
print("patched")
