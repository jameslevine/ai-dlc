plugins { kotlin("jvm") version "2.1.0" }

kotlin {
    jvmToolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
