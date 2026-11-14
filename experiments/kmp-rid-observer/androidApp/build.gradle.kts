plugins { id("com.android.application") }
android {
    namespace = "org.smri.ridobserver.kmp"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.smri.ridobserver.kmp"
        minSdk = 24
        targetSdk = 36
        versionCode = 10
        versionName = "0.10-field-location"
        testInstrumentationRunner = "org.smri.ridobserver.kmp.FieldTestInstrumentation"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies { implementation(project(":shared")) }
