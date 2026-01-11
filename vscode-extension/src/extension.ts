import * as vscode from 'vscode';
import { SidebarProvider } from './SidebarProvider';
import { BackendClient } from './BackendClient';

export function activate(context: vscode.ExtensionContext) {
    console.log('Agentic IDE extension is now active!');

    // Get backend URL from settings
    const config = vscode.workspace.getConfiguration('agenticIDE');
    const backendUrl = config.get<string>('backendUrl') || 'https://web-production-ff3c3.up.railway.app';

    // Detailed logging for backend URL
    console.log('===========================================');
    console.log('🌐 BACKEND URL CONFIGURATION:');
    console.log('Backend URL:', backendUrl);
    console.log('Config value:', config.get<string>('backendUrl'));
    console.log('Using default?', !config.get<string>('backendUrl'));
    console.log('===========================================');

    // Initialize backend client
    const backendClient = new BackendClient(backendUrl);

    // Create sidebar provider (now used for panel)
    const sidebarProvider = new SidebarProvider(context.extensionUri, backendClient);

    // Register the panel webview
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            'agentic-ide.chatView',
            sidebarProvider
        )
    );

    // Register command: Open Panel
    context.subscriptions.push(
        vscode.commands.registerCommand('agentic-ide.startWorkflow', async () => {
            // Focus on the panel view
            await vscode.commands.executeCommand('agentic-ide.chatView.focus');
        })
    );

    // Status bar item
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    statusBarItem.text = "$(robot) Agentic IDE";
    statusBarItem.tooltip = "Click to open Agentic IDE Chat";
    statusBarItem.command = 'agentic-ide.startWorkflow';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    console.log('Agentic IDE: Panel view registered');
}

export function deactivate() {
    console.log('Agentic IDE extension deactivated');
}