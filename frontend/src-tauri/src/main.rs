// APHELIOS – Tauri-Einstiegspunkt (Windows-Desktop-Shell).
// Lädt das Vite-Frontend in ein randloses, transparentes Fenster.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("Fehler beim Start von APHELIOS");
}
