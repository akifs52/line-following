package org.qtproject.example;

import android.content.Context;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;

public class HapticFeedbackHelper {
    private static HapticFeedbackHelper instance;
    private Context context;
    private Vibrator vibrator;

    public HapticFeedbackHelper(Context context) {
        this.context = context;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            VibratorManager vibratorManager = (VibratorManager) context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE);
            if (vibratorManager != null) {
                this.vibrator = vibratorManager.getDefaultVibrator();
            }
        } else {
            this.vibrator = (Vibrator) context.getSystemService(Context.VIBRATOR_SERVICE);
        }
    }

    public static void init(Context context) {
        if (instance == null) {
            instance = new HapticFeedbackHelper(context);
        }
    }

    public static void performHapticFeedback(int type) {
        if (instance == null || instance.vibrator == null) return;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            int effectType;
            switch (type) {
                case 1: // Light
                    effectType = VibrationEffect.EFFECT_CLICK;
                    break;
                case 2: // Medium
                    effectType = VibrationEffect.EFFECT_TICK;
                    break;
                case 3: // Heavy
                    effectType = VibrationEffect.EFFECT_HEAVY_CLICK;
                    break;
                case 4: // Double
                    effectType = VibrationEffect.EFFECT_DOUBLE_CLICK;
                    break;
                default:
                    effectType = VibrationEffect.EFFECT_CLICK;
                    break;
            }
            instance.vibrator.vibrate(VibrationEffect.createPredefined(effectType));
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            long[] pattern;
            switch (type) {
                case 1: // Light
                    pattern = new long[]{0, 10};
                    break;
                case 2: // Medium
                    pattern = new long[]{0, 20};
                    break;
                case 3: // Heavy
                    pattern = new long[]{0, 50};
                    break;
                case 4: // Double
                    pattern = new long[]{0, 30, 50, 30};
                    break;
                default:
                    pattern = new long[]{0, 20};
                    break;
            }
            instance.vibrator.vibrate(VibrationEffect.createWaveform(pattern, -1));
        } else {
            // Fallback for older devices
            switch (type) {
                case 1:
                    instance.vibrator.vibrate(10);
                    break;
                case 2:
                    instance.vibrator.vibrate(20);
                    break;
                case 3:
                    instance.vibrator.vibrate(50);
                    break;
                case 4:
                    instance.vibrator.vibrate(new long[]{0, 30, 50, 30}, -1);
                    break;
                default:
                    instance.vibrator.vibrate(20);
                    break;
            }
        }
    }
}
