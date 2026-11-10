plugins { id("com.android.application") }
android {
    namespace = "org.smri.ridobserver.kmp"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.smri.ridobserver.kmp"
        minSdk = 30
        targetSdk = 36
        versionCode = 6
        versionName = "0.6-local-database"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies { implementation(project(":shared")) }
