from pathlib import Path
import re, sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "DrFocus")
main = root / "app/src/main/java/com/drahmed/drfocus/MainActivity.kt"
svc = root / "app/src/main/java/com/drahmed/drfocus/service/FocusAccessibilityService.kt"
core = root / "app/src/main/java/com/drahmed/drfocus/core"

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")

controller = r'''package com.drahmed.drfocus.core

import android.accessibilityservice.AccessibilityService
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.os.UserManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Personal-build strict protections. System user restrictions are applied only
 * when Android has provisioned DrFocus as Device Owner/Profile Owner. Otherwise
 * Accessibility provides a best-effort UI shield.
 */
object StrictDeviceControl {
    private const val PREFS = "drfocus_strict_device_control"
    private const val K_ACTIVE = "strict_active"
    private const val K_CLEAR_DATA = "prevent_clear_data"
    private const val K_UNINSTALL = "prevent_uninstall_apps"
    private const val K_INSTALL = "prevent_install_apps"
    private const val K_APPLIED_APPS_CONTROL = "applied_apps_control"
    private const val K_APPLIED_UNINSTALL = "applied_uninstall"
    private const val K_APPLIED_INSTALL = "applied_install"

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun isStrictMarkedActive(context: Context): Boolean = prefs(context).getBoolean(K_ACTIVE, false)
    fun preventClearData(context: Context): Boolean = prefs(context).getBoolean(K_CLEAR_DATA, false)
    fun preventUninstallApps(context: Context): Boolean = prefs(context).getBoolean(K_UNINSTALL, false)
    fun preventInstallApps(context: Context): Boolean = prefs(context).getBoolean(K_INSTALL, false)

    fun setPreventClearData(context: Context, enabled: Boolean) = setMonotonic(context, K_CLEAR_DATA, enabled)
    fun setPreventUninstallApps(context: Context, enabled: Boolean) = setMonotonic(context, K_UNINSTALL, enabled)
    fun setPreventInstallApps(context: Context, enabled: Boolean) = setMonotonic(context, K_INSTALL, enabled)

    private fun setMonotonic(context: Context, key: String, enabled: Boolean) {
        val p = prefs(context)
        // During Strict Mode protections can be strengthened, not weakened.
        if (p.getBoolean(K_ACTIVE, false) && p.getBoolean(key, false) && !enabled) return
        p.edit().putBoolean(key, enabled).apply()
        if (p.getBoolean(K_ACTIVE, false)) applyOwnerRestrictions(context, true)
    }

    fun syncStrictState(context: Context, active: Boolean) {
        val p = prefs(context)
        if (p.getBoolean(K_ACTIVE, false) != active) p.edit().putBoolean(K_ACTIVE, active).apply()
        applyOwnerRestrictions(context, active)
    }

    fun fullSystemControlAvailable(context: Context): Boolean {
        val dpm = context.getSystemService(DevicePolicyManager::class.java) ?: return false
        return dpm.isDeviceOwnerApp(context.packageName) || dpm.isProfileOwnerApp(context.packageName)
    }

    private fun ownAdmin(context: Context, dpm: DevicePolicyManager): ComponentName? =
        dpm.activeAdmins?.firstOrNull { it.packageName == context.packageName }

    private fun applyOwnerRestrictions(context: Context, active: Boolean) {
        val dpm = context.getSystemService(DevicePolicyManager::class.java) ?: return
        if (!fullSystemControlAvailable(context)) return
        val admin = ownAdmin(context, dpm) ?: return
        val p = prefs(context)
        try {
            reconcileRestriction(
                dpm, admin, p, K_APPLIED_APPS_CONTROL, UserManager.DISALLOW_APPS_CONTROL,
                active && preventClearData(context)
            )
            reconcileRestriction(
                dpm, admin, p, K_APPLIED_UNINSTALL, UserManager.DISALLOW_UNINSTALL_APPS,
                active && preventUninstallApps(context)
            )
            reconcileRestriction(
                dpm, admin, p, K_APPLIED_INSTALL, UserManager.DISALLOW_INSTALL_APPS,
                active && preventInstallApps(context)
            )
        } catch (_: SecurityException) {
            // Device Admin alone cannot set these user restrictions.
        } catch (_: RuntimeException) {
            // Keep the blocker alive on OEM-specific policy failures.
        }
    }

    private fun reconcileRestriction(
        dpm: DevicePolicyManager,
        admin: ComponentName,
        p: android.content.SharedPreferences,
        appliedKey: String,
        restriction: String,
        shouldApply: Boolean
    ) {
        val applied = p.getBoolean(appliedKey, false)
        when {
            shouldApply && !applied -> {
                dpm.addUserRestriction(admin, restriction)
                p.edit().putBoolean(appliedKey, true).apply()
            }
            !shouldApply && applied -> {
                dpm.clearUserRestriction(admin, restriction)
                p.edit().putBoolean(appliedKey, false).apply()
            }
        }
    }

    fun shouldShield(context: Context, event: AccessibilityEvent, root: AccessibilityNodeInfo?): Boolean {
        if (!isStrictMarkedActive(context)) return false
        val pkg = (event.packageName?.toString() ?: "").lowercase()
        val text = buildString {
            event.text.forEach { append(it).append(' ') }
            event.contentDescription?.let { append(it).append(' ') }
            collectText(root, this, 0)
        }.lowercase()
        return shouldShieldSurface(
            packageName = pkg,
            visibleText = text,
            preventClearData = preventClearData(context),
            preventUninstall = preventUninstallApps(context),
            preventInstall = preventInstallApps(context)
        )
    }

    internal fun shouldShieldSurface(
        packageName: String,
        visibleText: String,
        preventClearData: Boolean,
        preventUninstall: Boolean,
        preventInstall: Boolean
    ): Boolean {
        val pkg = packageName.lowercase()
        val text = visibleText.lowercase()
        val settings = pkg.contains("settings") || pkg.contains("permissioncontroller")
        val installer = pkg.contains("packageinstaller") || pkg.contains("package.installer")
        val playStore = pkg == "com.android.vending"

        val uninstallWords = listOf(
            "uninstall", "do you want to uninstall", "remove app",
            "إلغاء التثبيت", "الغاء التثبيت", "إزالة التطبيق", "حذف التطبيق"
        )
        val clearDataWords = listOf(
            "clear data", "clear storage", "delete app data", "erase data",
            "مسح البيانات", "حذف البيانات", "محو البيانات", "مسح مساحة التخزين"
        )
        val installWords = listOf(
            "install", "install app", "do you want to install", "package installer",
            "تثبيت", "تثبيت التطبيق", "هل تريد تثبيت"
        )

        if (preventClearData && settings && clearDataWords.any(text::contains)) return true
        if (preventUninstall && (settings || installer) && uninstallWords.any(text::contains)) return true
        if (preventInstall && installer && installWords.any(text::contains)) return true
        // Keep Play Store browsing available; stop only install surfaces.
        if (preventInstall && playStore && installWords.any(text::contains)) return true
        return false
    }

    private fun collectText(node: AccessibilityNodeInfo?, out: StringBuilder, depth: Int) {
        if (node == null || depth > 18) return
        node.text?.let { out.append(it).append(' ') }
        node.contentDescription?.let { out.append(it).append(' ') }
        for (i in 0 until node.childCount) {
            val child = runCatching { node.getChild(i) }.getOrNull()
            collectText(child, out, depth + 1)
            child?.recycle()
        }
    }
}
'''
(core / "StrictDeviceControl.kt").write_text(controller, encoding="utf-8")

testdir = root / "app/src/test/java/com/drahmed/drfocus/core"
testdir.mkdir(parents=True, exist_ok=True)
(testdir / "StrictDeviceControlTest.kt").write_text(r'''package com.drahmed.drfocus.core

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StrictDeviceControlTest {
    @Test fun blocksClearDataInSettingsArabicAndEnglish() {
        assertTrue(StrictDeviceControl.shouldShieldSurface("com.android.settings", "مسح البيانات", true, false, false))
        assertTrue(StrictDeviceControl.shouldShieldSurface("com.android.settings", "Clear storage", true, false, false))
        assertFalse(StrictDeviceControl.shouldShieldSurface("com.android.settings", "Wi-Fi", true, false, false))
    }

    @Test fun blocksUninstallButNotNormalSettings() {
        assertTrue(StrictDeviceControl.shouldShieldSurface("com.android.settings", "إلغاء التثبيت", false, true, false))
        assertTrue(StrictDeviceControl.shouldShieldSurface("com.google.android.packageinstaller", "Do you want to uninstall?", false, true, false))
        assertFalse(StrictDeviceControl.shouldShieldSurface("com.android.settings", "Battery", false, true, false))
    }

    @Test fun blocksInstallSurfaceWithoutBlockingStoreBrowsing() {
        assertTrue(StrictDeviceControl.shouldShieldSurface("com.google.android.packageinstaller", "Install app", false, false, true))
        assertTrue(StrictDeviceControl.shouldShieldSurface("com.android.vending", "تثبيت", false, false, true))
        assertFalse(StrictDeviceControl.shouldShieldSurface("com.android.vending", "Games for you", false, false, true))
    }
}
''', encoding="utf-8")

s = read(main)
if "preventClearAppData by remember" not in s:
    m = re.search(r'(?m)^(\s*)var\s+preventRestart\b[^\n]*$', s)
    if not m: raise SystemExit("Could not find preventRestart state declaration")
    indent = m.group(1)
    block = m.group(0) + "\n" + \
        indent + 'var preventClearAppData by remember { mutableStateOf(com.drahmed.drfocus.core.StrictDeviceControl.preventClearData(context)) }\n' + \
        indent + 'var preventUninstallApps by remember { mutableStateOf(com.drahmed.drfocus.core.StrictDeviceControl.preventUninstallApps(context)) }\n' + \
        indent + 'var preventInstallApps by remember { mutableStateOf(com.drahmed.drfocus.core.StrictDeviceControl.preventInstallApps(context)) }'
    s = s[:m.start()] + block + s[m.end():]

if "منع حذف بيانات التطبيقات" not in s:
    m = re.search(r'(?m)^(\s*)([^\n]*منع إعادة تشغيل الهاتف[^\n]*)$', s)
    if not m: raise SystemExit("Could not find restart toggle line")
    ind = m.group(1)
    rows = (
        ind + 'ToggleRow("منع حذف بيانات التطبيقات", "يمنع مسح بيانات التطبيقات أثناء الوضع الصارم. Device Owner يطبق حماية نظامية أقوى.", preventClearAppData, onChecked = { value -> preventClearAppData = value; com.drahmed.drfocus.core.StrictDeviceControl.setPreventClearData(context, value) })\n' +
        ind + 'ToggleRow("منع إلغاء تثبيت التطبيقات", "يحمي التطبيقات من الإزالة أثناء الوضع الصارم، مع حماية نظامية كاملة عند توفر Device Owner.", preventUninstallApps, onChecked = { value -> preventUninstallApps = value; com.drahmed.drfocus.core.StrictDeviceControl.setPreventUninstallApps(context, value) })\n' +
        ind + 'ToggleRow("منع تثبيت تطبيقات جديدة", "يمنع شاشات التثبيت أثناء الوضع الصارم، ويستخدم سياسة Android الرسمية عند توفر Device Owner.", preventInstallApps, onChecked = { value -> preventInstallApps = value; com.drahmed.drfocus.core.StrictDeviceControl.setPreventInstallApps(context, value) })\n'
    )
    s = s[:m.start()] + rows + s[m.start():]

if "StrictDeviceControl.syncStrictState" not in s:
    m = re.search(r'(?m)^(\s*)(?:val|var)\s+(strict(?:Mode)?Active)\s*=\s*([^\n]+)$', s, re.I)
    if m:
        ind, name = m.group(1), m.group(2)
        s = s[:m.end()] + '\n' + ind + 'LaunchedEffect(' + name + ') { com.drahmed.drfocus.core.StrictDeviceControl.syncStrictState(context, ' + name + ') }' + s[m.end():]
    else:
        ms = re.search(r'(?m)^(\s*)(?:val|var)\s+(strict\w*state)\s*=\s*([^\n]+)$', s, re.I)
        if not ms: raise SystemExit("Could not find strict active/state declaration for sync")
        ind, name = ms.group(1), ms.group(2)
        s = s[:ms.end()] + '\n' + ind + 'LaunchedEffect(' + name + ') { com.drahmed.drfocus.core.StrictDeviceControl.syncStrictState(context, ' + name + '.active) }' + s[ms.end():]
write(main, s)

s = read(svc)
if "StrictDeviceControl.shouldShield(this, event" not in s:
    m = re.search(r'(override\s+fun\s+onAccessibilityEvent\s*\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)', s)
    if not m: raise SystemExit("Could not find onAccessibilityEvent")
    inject = r'''
        if (event != null && com.drahmed.drfocus.core.StrictDeviceControl.shouldShield(this, event, rootInActiveWindow)) {
            performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
            android.widget.Toast.makeText(this, "محمي بواسطة DrFocus أثناء الوضع الصارم", android.widget.Toast.LENGTH_SHORT).show()
            return
        }
'''
    s = s[:m.end()] + inject + s[m.end():]
write(svc, s)

gradle = root / "app/build.gradle.kts"
g = read(gradle)
g = re.sub(r'versionCode\s*=\s*\d+', 'versionCode = 14', g, count=1)
g = re.sub(r'versionName\s*=\s*"[^"]+"', 'versionName = "1.4.0-personal"', g, count=1)
write(gradle, g)

readme = root / "README.md"
r = read(readme)
if "DrFocus 1.4 Personal" not in r:
    r += "\n\n## DrFocus 1.4 Personal\nStrict Mode adds optional protection against clearing app data, uninstalling apps, and installing new apps. Device Owner/Profile Owner uses Android user restrictions; ordinary Device Admin falls back to a narrow Accessibility UI shield. Protections cannot be weakened while Strict Mode is active.\n"
write(readme, r)

print("DrFocus 1.4 transformation applied")
