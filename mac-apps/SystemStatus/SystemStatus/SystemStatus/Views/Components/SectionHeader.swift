//
//  SectionHeader.swift
//  SystemStatus
//
//  Standard section header with icon, title, and copy-to-clipboard button.
//

import SwiftUI

/// Standard section header row: icon + title on the left, copy-to-clipboard on the right.
struct SectionHeader: View {
    let title: String
    let systemImage: String
    let copyText: String
    @State private var copied = false

    var body: some View {
        HStack {
            Label(title, systemImage: systemImage)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(copyText, forType: .string)
                withAnimation { copied = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                    withAnimation { copied = false }
                }
            } label: {
                Image(systemName: copied ? "checkmark" : "doc.on.clipboard")
                    .font(.system(size: 10))
                    .foregroundStyle(copied ? .green : .secondary)
            }
            .buttonStyle(.plain)
            .help("Copy to clipboard")
        }
    }
}
