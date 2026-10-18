package com.machinist.todoro

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Разбор ответа GitHub о выпуске (parseRelease, assetUrl) — без интернета: ответы собраны здесь же.
 * Robolectric — потому что JSONObject входит в Android.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UpdatesTest {
    private val sha = "0123456789abcdef".repeat(4)  // 64 знака
    private val apkUrl = "https://github.com/machinist-soft/ToDoro/releases/download/v2.18/ToDoro.apk"
    private val jsonUrl = "https://github.com/machinist-soft/ToDoro/releases/download/v2.18/ToDoro-android.json"
    private val page = "https://github.com/machinist-soft/ToDoro/releases/tag/v2.18"

    private fun asset(name: String, url: String, digest: String? = null, size: Long = 0) = JSONObject().apply {
        put("name", name)
        put("browser_download_url", url)
        if (digest != null) put("digest", digest)
        put("size", size)
    }

    private fun release(vararg assets: JSONObject, htmlUrl: String? = page) = JSONObject().apply {
        put("tag_name", "v2.18")
        if (htmlUrl != null) put("html_url", htmlUrl)
        put("assets", JSONArray().apply { assets.forEach { put(it) } })
    }

    private fun normal() = release(
        asset("ToDoro-Setup-2.18.exe", "https://example.org/setup.exe", "sha256:" + "f".repeat(64)),
        asset("ToDoro.apk", apkUrl, "sha256:$sha", 5_000_000),
        asset("ToDoro-android.json", jsonUrl, "sha256:" + "a".repeat(64)),
    )

    private fun version(code: Any? = 8, name: String? = "0.8") = JSONObject().apply {
        if (code != null) put("versionCode", code)
        if (name != null) put("versionName", name)
    }

    @Test
    fun normalRelease() {
        val r = parseRelease(normal(), version())
        assertEquals(AppRelease(8, "0.8", apkUrl, sha, 5_000_000, page), r)
    }

    @Test
    fun noVersionCode() {
        assertNull(parseRelease(normal(), version(code = null)))
        assertNull(parseRelease(normal(), JSONObject()))
    }

    @Test
    fun zeroOrNegativeOrBrokenVersionCode() {
        assertNull(parseRelease(normal(), version(code = 0)))
        assertNull(parseRelease(normal(), version(code = -3)))
        assertNull(parseRelease(normal(), version(code = "восемь")))
    }

    @Test
    fun bigVersionCode() {
        assertEquals(3_000_000_000L, parseRelease(normal(), version(code = 3_000_000_000L))!!.versionCode)
    }

    @Test
    fun noApkInRelease() {
        val r = release(asset("ToDoro-android.json", jsonUrl), asset("ToDoro-0.8.apk", apkUrl, "sha256:$sha"))
        assertNull(parseRelease(r, version()))
    }

    @Test
    fun noAssetsAtAll() {
        assertNull(parseRelease(JSONObject().put("html_url", page), version()))
        assertNull(parseRelease(release(), version()))
    }

    @Test
    fun noDigest() {
        assertNull(parseRelease(release(asset("ToDoro.apk", apkUrl)), version()))
        // в JSON у GitHub бывает "digest": null (старые выпуски)
        val withNull = release(asset("ToDoro.apk", apkUrl).put("digest", JSONObject.NULL))
        assertNull(parseRelease(withNull, version()))
    }

    @Test
    fun badDigest() {
        for (digest in listOf(
            "", "sha256:", "sha256:" + sha.dropLast(1), "sha256:" + sha + "0",
            "sha256:" + "g".repeat(64), "sha512:" + sha + sha, "md5:" + sha, "sha256: $sha",
        )) {
            assertNull("digest «$digest»", parseRelease(release(asset("ToDoro.apk", apkUrl, digest)), version()))
        }
    }

    @Test
    fun upperCaseDigestIsLowered() {
        val r = parseRelease(release(asset("ToDoro.apk", apkUrl, "sha256:" + sha.uppercase())), version())
        assertEquals(sha, r!!.apkSha256)
    }

    @Test
    fun httpLinkIsRefused() {
        val http = apkUrl.replace("https://", "http://")
        assertNull(parseRelease(release(asset("ToDoro.apk", http, "sha256:$sha")), version()))
        assertNull(parseRelease(release(asset("ToDoro.apk", "", "sha256:$sha")), version()))
        assertNull(parseRelease(release(asset("ToDoro.apk", "ftp://x/ToDoro.apk", "sha256:$sha")), version()))
    }

    @Test
    fun emptyVersionNameBecomesCode() {
        assertEquals("8", parseRelease(normal(), version(name = ""))!!.versionName)
        assertEquals("8", parseRelease(normal(), version(name = null))!!.versionName)
    }

    @Test
    fun noPageGivesReleasesList() {
        val r = release(asset("ToDoro.apk", apkUrl, "sha256:$sha"), htmlUrl = null)
        assertEquals(Updates.RELEASES_URL, parseRelease(r, version())!!.page)
    }

    @Test
    fun noSizeIsZero() {
        val a = JSONObject().put("name", "ToDoro.apk").put("browser_download_url", apkUrl).put("digest", "sha256:$sha")
        assertEquals(0L, parseRelease(release(a), version())!!.apkSize)
    }

    @Test
    fun assetUrlFindsFileByName() {
        assertEquals(jsonUrl, assetUrl(normal(), Updates.VERSION_FILE))
        assertEquals(apkUrl, assetUrl(normal(), Updates.APK_NAME))
    }

    @Test
    fun assetUrlMissing() {
        assertNull(assetUrl(normal(), "нет-такого.json"))
        assertNull(assetUrl(release(), Updates.VERSION_FILE))
        assertNull(assetUrl(JSONObject(), Updates.VERSION_FILE))
        // файл есть, но без ссылки
        assertNull(assetUrl(release(JSONObject().put("name", Updates.VERSION_FILE)), Updates.VERSION_FILE))
    }

    @Test
    fun assetUrlNameIsExact() {
        val r = release(asset("todoro-android.json", "https://x/1"), asset("ToDoro-android.json.bak", "https://x/2"))
        assertNull(assetUrl(r, Updates.VERSION_FILE))
        assertNotNull(assetUrl(release(asset("ToDoro-android.json", "https://x/3")), Updates.VERSION_FILE))
    }
}
