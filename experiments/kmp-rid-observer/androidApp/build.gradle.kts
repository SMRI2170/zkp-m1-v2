plugins { id("com.android.application") }
android {
    namespace = "org.smri.ridobserver.kmp"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.smri.ridobserver.kmp"
        minSdk = 24
        targetSdk = 36
        versionCode = 14
        versionName = "0.14-segmented-storage"
        testInstrumentationRunner = "org.smri.ridobserver.kmp.FieldTestInstrumentation"
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies { implementation(project(":shared")) }
