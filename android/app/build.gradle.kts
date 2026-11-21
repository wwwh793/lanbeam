plugins {
    id("com.android.application")
}

android {
    namespace = "com.moyuli.lanbeam"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.moyuli.lanbeam"
        minSdk = 24
        targetSdk = 35
        versionCode = 1000001
        versionName = "1.0.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

// 本项目不依赖任何第三方库（不用 AndroidX），所以没有 dependencies 块。
