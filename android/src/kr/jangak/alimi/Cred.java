package kr.jangak.alimi;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * 학교 포털 자동 로그인용 아이디·비밀번호 (포털마다 따로: hyin = 한양 포털, kcloud = 강원대 K-Cloud).
 * 안드로이드 키 저장소(Keystore)의 꺼낼 수 없는 키로 암호화해 이 앱 안에만 둔다. 서버나 다른 곳으로 보내지 않는다.
 */
final class Cred {
    private static final String ALIAS = "jangak_portal_login";
    private Cred() { }

    private static String sfx(String k) { return "hyin".equals(k) ? "" : "_" + k; }

    private static SharedPreferences sp(Context c, String k) { return c.getSharedPreferences("portal_login" + sfx(k), Context.MODE_PRIVATE); }

    private static SecretKey key(String k) throws Exception {
        String alias = ALIAS + sfx(k);
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(alias)) return ((KeyStore.SecretKeyEntry) ks.getEntry(alias, null)).getSecretKey();
        KeyGenerator g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        g.init(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build());
        return g.generateKey();
    }

    static void save(Context c, String id, String pw) throws Exception { save(c, "hyin", id, pw); }

    static void save(Context c, String k, String id, String pw) throws Exception {
        Cipher ci = Cipher.getInstance("AES/GCM/NoPadding");
        ci.init(Cipher.ENCRYPT_MODE, key(k));
        byte[] ct = ci.doFinal(new JSONObject().put("id", id).put("pw", pw).toString().getBytes(StandardCharsets.UTF_8));
        sp(c, k).edit().putString("iv", Base64.encodeToString(ci.getIV(), Base64.NO_WRAP))
                .putString("ct", Base64.encodeToString(ct, Base64.NO_WRAP)).putString("state", "on").apply();
    }

    /** {id, pw} 또는 null. */
    static JSONObject load(Context c) { return load(c, "hyin"); }

    static JSONObject load(Context c, String k) {
        try {
            String iv = sp(c, k).getString("iv", null), ct = sp(c, k).getString("ct", null);
            if (iv == null || ct == null) return null;
            Cipher ci = Cipher.getInstance("AES/GCM/NoPadding");
            ci.init(Cipher.DECRYPT_MODE, key(k), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
            return new JSONObject(new String(ci.doFinal(Base64.decode(ct, Base64.NO_WRAP)), StandardCharsets.UTF_8));
        } catch (Exception e) {
            return null;
        }
    }

    static boolean has(Context c, String k) { return sp(c, k).contains("ct"); }

    /** on / failed / off */
    static String state(Context c) { return state(c, "hyin"); }

    static String state(Context c, String k) { return has(c, k) ? sp(c, k).getString("state", "on") : "off"; }

    static void setState(Context c, String s) { setState(c, "hyin", s); }

    static void setState(Context c, String k, String s) { sp(c, k).edit().putString("state", s).apply(); }

    static void clear(Context c) { clear(c, "hyin"); }

    static void clear(Context c, String k) {
        sp(c, k).edit().clear().apply();
        try { KeyStore ks = KeyStore.getInstance("AndroidKeyStore"); ks.load(null); ks.deleteEntry(ALIAS + sfx(k)); } catch (Exception ignored) { }
    }
}
