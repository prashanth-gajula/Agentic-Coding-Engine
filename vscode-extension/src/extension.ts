import * as path from 'path';
import * as dotenv from 'dotenv';
import * as vscode from 'vscode';
import { SidebarProvider } from './SidebarProvider';
import { BackendClient } from './BackendClient';

export function activate(context: vscode.ExtensionContext) {
    // Load .env file from extension root directory
    const envPath = path.join(context.extensionPath, '.env');
    dotenv.config({ path: envPath });
    
    console.log('Agentic IDE extension is now active!');

    // Get backend URL from .env, then fall back to VS Code settings, then default to localhost
    const config = vscode.workspace.getConfiguration('agenticIDE');
    const backendUrl = process.env.BACKEND_URL || 
                      config.get<string>('backendUrl') || 
                      'http://localhost:8000';

    // Detailed logging for backend URL
    console.log('===========================================');
    console.log('🌐 BACKEND URL CONFIGURATION:');
    console.log('Backend URL:', backendUrl);
    console.log('Config value:', config.get<string>('backendUrl'));
    console.log('Environment variable:', process.env.BACKEND_URL || 'not set');
    console.log('Source:', process.env.BACKEND_URL ? '.env file' : (config.get<string>('backendUrl') ? 'VS Code settings' : 'default (localhost)'));
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