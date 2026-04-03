//
//  AboutView.swift
//  SystemStatus
//
//  Displayed in a dedicated non-resizable window opened from the popover footer.
//

import SwiftUI

struct AboutView: View {
    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    private var build: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
    }

    private var copyrightYear: String {
        let year = Calendar.current.component(.year, from: Date())
        return "© \(year) Anirban Bagchi"
    }

    var body: some View {
        VStack(spacing: 0) {
            // App icon + name + version
            VStack(spacing: 12) {
                Image(nsImage: NSApp.applicationIconImage)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 80, height: 80)

                VStack(spacing: 4) {
                    Text("SystemStatus")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("Version \(version) (\(build))")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
            .padding(.top, 28)
            .padding(.bottom, 16)

            Divider()

            // Description
            Text("A lightweight macOS menu bar app that monitors CPU, GPU,  Memory, Network, Disk, Battery and system statistics — no Dock icon, no clutter.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 24)
                .padding(.vertical, 16)

            Divider()

            // Footer
            Text(copyrightYear)
                .font(.footnote)
                .foregroundStyle(.tertiary)
                .padding(.vertical, 12)
        }
        .frame(width: 320)
    }
}

#Preview {
    AboutView()
}
