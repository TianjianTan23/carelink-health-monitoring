package com.carelink.coursework;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Only authenticated ciphertext is stored in preferences; key never leaves Keystore. */
final class SessionVault {
    private static final String ALIAS="carelink.session.v1";
    private final SharedPreferences prefs;
    SessionVault(Context context){prefs=context.getSharedPreferences("carelink_encrypted_session",Context.MODE_PRIVATE);}
    private SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(!store.containsAlias(ALIAS)){
            // Missing key plus ciphertext is corruption/key invalidation, not a fresh install.
            if(prefs.contains("ciphertext"))throw new IllegalStateException("Credential storage unavailable");
            KeyGenerator gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            gen.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build());gen.generateKey();
        }
        return (SecretKey)store.getKey(ALIAS,null);
    }
    synchronized void write(String value) throws Exception {
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
        cipher.updateAAD("CareLink-session-v1".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        byte[] data=cipher.doFinal(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        if(!prefs.edit().putString("ciphertext",Base64.encodeToString(data,Base64.NO_WRAP))
            .putString("iv",Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)).commit())throw new IllegalStateException("Credential storage unavailable");
    }
    synchronized String read() throws Exception {
        if(!prefs.contains("ciphertext"))return null;
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(prefs.getString("iv",""),Base64.NO_WRAP)));
        cipher.updateAAD("CareLink-session-v1".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        return new String(cipher.doFinal(Base64.decode(prefs.getString("ciphertext",""),Base64.NO_WRAP)),java.nio.charset.StandardCharsets.UTF_8);
    }
    synchronized void clear(){if(!prefs.edit().clear().commit())throw new IllegalStateException("Credential cleanup failed");}
}
