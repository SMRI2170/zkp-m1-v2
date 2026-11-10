import org.jetbrains.kotlin.gradle.dsl.JvmTarget
plugins {
    kotlin("multiplatform")
    id("com.android.kotlin.multiplatform.library")
}
kotlin {
    android {
        namespace = "org.smri.ridobserver.shared"
        compileSdk = 36
        minSdk = 30
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
        withHostTest {}
    }
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }
    sourceSets { commonTest.dependencies { implementation(kotlin("test")) } }
}
