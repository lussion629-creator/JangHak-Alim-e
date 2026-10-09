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
 * 한양 포털 자동 로그인용 아이디·비밀번호.
 * 안드로이드 키 저장소(Keystore)의 꺼낼 수 없는 키로 암호화해 이 앱 안에만 둔다. 서버나 다른 곳으로 보내지 않는다.
 */
final class Cred {
    private static final String ALIAS = "jangak_portal_login";
    private Cred() { }

    private static SharedPreferences sp(Context c) { return c.getSharedPreferences("portal_login", Context.MODE_PRIVATE); }

    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(ALIAS)) return ((KeyStore.SecretKeyEntry) ks.getEntry(ALIAS, null)).getSecretKey();
        KeyGenerator g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        g.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build());
        return g.generateKey();
    }

    static void save(Context c, String id, String pw) throws Exception {
        Cipher ci = Cipher.getInstance("AES/GCM/NoPadding");
        ci.init(Cipher.ENCRYPT_MODE, key());
        byte[] ct = ci.doFinal(new JSONObject().put("id", id).put("pw", pw).toString().getBytes(StandardCharsets.UTF_8));
        sp(c).edit().putString("iv", Base64.encodeToString(ci.getIV(), Base64.NO_WRAP))
                .putString("ct", Base64.encodeToString(ct, Base64.NO_WRAP)).putString("state", "on").apply();
    }

    /** {id, pw} 또는 null. */
    static JSONObject load(Context c) {
        try {
            String iv = sp(c).getString("iv", null), ct = sp(c).getString("ct", null);
            if (iv == null || ct == null) return null;
            Cipher ci = Cipher.getInstance("AES/GCM/NoPadding");
            ci.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
            return new JSONObject(new String(ci.doFinal(Base64.decode(ct, Base64.NO_WRAP)), StandardCharsets.UTF_8));
        } catch (Exception e) {
            return null;
        }
    }

    static boolean has(Context c) { return sp(c).contains("ct"); }

    /** on / failed / off */
    static String state(Context c) { return has(c) ? sp(c).getString("state", "on") : "off"; }

    static void setState(Context c, String s) { sp(c).edit().putString("state", s).apply(); }

    static void clear(Context c) {
        sp(c).edit().clear().apply();
        try { KeyStore ks = KeyStore.getInstance("AndroidKeyStore"); ks.load(null); ks.deleteEntry(ALIAS); } catch (Exception ignored) { }
    }
}
