import * as vscode from 'vscode';
import { BackendClient } from './BackendClient';

export class SidebarProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;
    private currentSessionId?: string;

    constructor(
        private readonly _extensionUri: vscode.Uri,
        private readonly backendClient: BackendClient
    ) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };

        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

        // Handle messages from the webview
        webviewView.webview.onDidReceiveMessage(async (data) => {
            console.log('=== Webview message received ===');
            console.log('Message type:', data.type);
            console.log('Message data:', data);
            
            switch (data.type) {
                case 'sendMessage':
                    await this.handleUserMessage(data.message);
                    break;
                case 'submitReview':
                    await this.handleReviewSubmission(data.feedback, data.action);
                    break;
                case 'openFile':
                    this.openFile(data.filePath);
                    break;
            }
        });
    }

    private async handleUserMessage(message: string) {
        console.log('=== handleUserMessage called ===');
        console.log('Message:', message);
        
        if (!this._view) {
            console.log('ERROR: No view available');
            return;
        }

        // Add user message to chat
        this._view.webview.postMessage({
            type: 'addMessage',
            role: 'user',
            content: message
        });

        // Show thinking indicator
        this._view.webview.postMessage({
            type: 'setThinking',
            thinking: true
        });

        try {
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
            if (!workspaceFolder) {
                throw new Error('Please open a workspace folder first');
            }

            console.log('Workspace folder:', workspaceFolder.uri.fsPath);
            console.log('Calling startWorkflow...');
            
            // Start workflow
            const session = await this.backendClient.startWorkflow(
                message,
                workspaceFolder.uri.fsPath
            );

            console.log('Session created:', session);
            this.currentSessionId = session.session_id;

            console.log('Connecting to WebSocket...');
            // Connect to WebSocket for real-time updates
            await this.connectToWorkflow();
            
            console.log('WebSocket connected successfully');

        } catch (error: any) {
            console.error('=== ERROR in handleUserMessage ===');
            console.error('Error object:', error);
            console.error('Error message:', error.message);
            console.error('Error stack:', error.stack);
            
            this._view.webview.postMessage({
                type: 'error',
                message: error.message || 'Failed to start workflow'
            });
            
            this._view.webview.postMessage({
                type: 'setThinking',
                thinking: false
            });
        }
    }

    private async connectToWorkflow() {
        console.log('=== connectToWorkflow called ===');
        console.log('Current session ID:', this.currentSessionId);
        
        if (!this.currentSessionId || !this._view) {
            console.log('ERROR: Missing session ID or view');
            return;
        }

        try {
            console.log('Calling backendClient.connectWebSocket...');
            
            await this.backendClient.connectWebSocket(this.currentSessionId, {
                onStepUpdate: (data) => {
                    console.log('WebSocket: Step update received', data);
                    this._view?.webview.postMessage({
                        type: 'stepUpdate',
                        step: data.current_step,
                        plan: data.plan,
                        agent: data.active_agent
                    });
                },
                onReviewRequired: (data) => {
                    console.log('WebSocket: Review required', data);
                    this._view?.webview.postMessage({
                        type: 'reviewRequired',
                        plan: data.plan,
                        files: data.generated_files
                    });
                    
                    this._view?.webview.postMessage({
                        type: 'setThinking',
                        thinking: false
                    });
                },
                onComplete: (data) => {
                    console.log('WebSocket: Workflow complete', data);
                    this._view?.webview.postMessage({
                        type: 'workflowComplete',
                        files: data.generated_files
                    });
                    
                    this._view?.webview.postMessage({
                        type: 'setThinking',
                        thinking: false
                    });
                },
                onError: (error) => {
                    console.error('WebSocket: Error received', error);
                    this._view?.webview.postMessage({
                        type: 'error',
                        message: error.message || 'An error occurred'
                    });
                    
                    this._view?.webview.postMessage({
                        type: 'setThinking',
                        thinking: false
                    });
                }
            });
            
            console.log('WebSocket connection completed');
        } catch (error: any) {
            console.error('=== ERROR in connectToWorkflow ===');
            console.error('Error object:', error);
            console.error('Error message:', error.message);
            console.error('Error stack:', error.stack);
            
            this._view?.webview.postMessage({
                type: 'error',
                message: 'Connection error: ' + error.message
            });
            
            this._view?.webview.postMessage({
                type: 'setThinking',
                thinking: false
            });
        }
    }

    private async handleReviewSubmission(feedback: string, action: 'approve' | 'revise') {
        console.log('=== handleReviewSubmission called ===');
        console.log('Action:', action);
        console.log('Feedback:', feedback);
        
        if (!this.currentSessionId || !this._view) {
            console.log('ERROR: Missing session ID or view');
            return;
        }

        try {
            await this.backendClient.submitReview(
                this.currentSessionId,
                feedback,
                action
            );

            if (action === 'approve') {
                this._view.webview.postMessage({
                    type: 'addMessage',
                    role: 'assistant',
                    content: '✅ Work approved! Workflow complete.'
                });
                
                this._view.webview.postMessage({
                    type: 'setThinking',
                    thinking: false
                });
            } else {
                // User requested changes
                this._view.webview.postMessage({
                    type: 'addMessage',
                    role: 'assistant',
                    content: '🔄 Creating new plan based on your feedback...'
                });
                
                this._view.webview.postMessage({
                    type: 'setThinking',
                    thinking: true
                });

                // Reconnect to continue workflow with new plan
                await this.connectToWorkflow();
            }
        } catch (error: any) {
            console.error('=== ERROR in handleReviewSubmission ===');
            console.error('Error:', error);
            
            this._view.webview.postMessage({
                type: 'error',
                message: error.message || 'Failed to submit review'
            });
            
            this._view.webview.postMessage({
                type: 'setThinking',
                thinking: false
            });
        }
    }

    private openFile(filePath: string) {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return;
        }

        const fullPath = vscode.Uri.joinPath(workspaceFolder.uri, filePath);
        vscode.workspace.openTextDocument(fullPath).then((doc) => {
            vscode.window.showTextDocument(doc);
        });
    }

    public _getHtmlForWebview(webview: vscode.Webview): string {
        return `<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Agentic IDE</title>
            <style>
                * {margin: 0; padding: 0; box-sizing: border-box;}
                body {font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); color: var(--vscode-foreground); background-color: var(--vscode-sidebar-background); height: 100vh; display: flex; flex-direction: column;}
                .header {padding: 12px 16px; border-bottom: 1px solid var(--vscode-panel-border); background: var(--vscode-sideBar-background);}
                .header h2 {font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px;}
                .messages-container {flex: 1; overflow-y: auto; padding: 16px;}
                .message {margin-bottom: 16px; padding: 12px; border-radius: 6px; animation: fadeIn 0.3s;}
                @keyframes fadeIn {from {opacity: 0; transform: translateY(10px);} to {opacity: 1; transform: translateY(0);}}
                .message.user {background-color: var(--vscode-input-background); border-left: 3px solid var(--vscode-inputOption-activeBackground);}
                .message.assistant {background-color: var(--vscode-editor-background); border-left: 3px solid var(--vscode-textLink-foreground);}
                .message .role {font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 6px; opacity: 0.8;}
                .message .content {line-height: 1.5; word-wrap: break-word;}
                .progress-list {margin-bottom: 16px; padding: 12px 16px; background: var(--vscode-editor-background); border-radius: 6px; display: none;}
                .progress-list.active {display: block;}
                .progress-list h4 {font-size: 12px; font-weight: 600; margin-bottom: 8px; opacity: 0.8;}
                .progress-step {padding: 6px 0; font-size: 12px; display: flex; align-items: flex-start; gap: 8px; line-height: 1.4;}
                .progress-step.completed {opacity: 0.7;}
                .progress-step.current {font-weight: 600; color: var(--vscode-textLink-activeForeground);}
                .step-icon {font-size: 14px; min-width: 16px; flex-shrink: 0;}
                .step-text {flex: 1;}
                .thinking-indicator {display: none; padding: 12px 16px; background: var(--vscode-editor-background); border-radius: 6px; margin-bottom: 16px;}
                .thinking-indicator.active {display: flex; align-items: center; gap: 8px;}
                .spinner {width: 16px; height: 16px; border: 2px solid var(--vscode-progressBar-background); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;}
                @keyframes spin {to {transform: rotate(360deg);}}
                .review-panel {background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 16px; margin-bottom: 16px; display: none;}
                .review-panel.active {display: block;}
                .review-files {margin: 12px 0; padding: 12px; background: var(--vscode-input-background); border-radius: 4px;}
                .review-files .file-item {padding: 4px 0; cursor: pointer; color: var(--vscode-textLink-foreground);}
                .review-files .file-item:hover {text-decoration: underline;}
                .review-textarea {width: 100%; min-height: 80px; padding: 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); border-radius: 4px; font-family: inherit; font-size: inherit; resize: vertical; margin: 12px 0;}
                .review-buttons {display: flex; gap: 8px;}
                .input-container {padding: 12px 16px; border-top: 1px solid var(--vscode-panel-border); background: var(--vscode-sideBar-background);}
                .input-wrapper {display: flex; gap: 8px;}
                textarea {flex: 1; padding: 8px 12px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); border-radius: 4px; font-family: inherit; font-size: inherit; resize: none; min-height: 40px; max-height: 120px;}
                button {padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: inherit; transition: background 0.2s;}
                button:hover {background: var(--vscode-button-hoverBackground);}
                button:disabled {opacity: 0.5; cursor: not-allowed;}
                button.secondary {background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);}
                .empty-state {text-align: center; padding: 40px 20px; color: var(--vscode-descriptionForeground);}
                .empty-state .icon {font-size: 48px; margin-bottom: 16px;}
            </style>
        </head>
        <body>
            <div class="header"><h2>🤖 Agentic IDE</h2></div>
            <div class="messages-container" id="messages">
                <div class="empty-state"><div class="icon">🤖</div><h3>Welcome to Agentic IDE</h3><p>Your AI-powered coding assistant with multi-agent workflow.</p></div>
            </div>
            <div class="progress-list" id="progressList">
                <h4>📋 Progress</h4>
                <div id="progressSteps"></div>
            </div>
            <div class="thinking-indicator" id="thinking"><div class="spinner"></div><span>AI is thinking...</span></div>
            <div class="review-panel" id="reviewPanel">
                <h3>🎉 Workflow Complete - Review Required</h3>
                <div class="review-files" id="reviewFiles"></div>
                <textarea id="reviewFeedback" class="review-textarea" placeholder="Leave empty to approve, or provide feedback..."></textarea>
                <div class="review-buttons"><button onclick="submitReview('approve')">✅ Approve</button><button class="secondary" onclick="submitReview('revise')">🔄 Request Changes</button></div>
            </div>
            <div class="input-container">
                <div class="input-wrapper"><textarea id="messageInput" placeholder="What would you like me to do?" rows="1"></textarea><button id="sendButton" onclick="sendMessage()">Send</button></div>
            </div>
            <script>
                const vscode=acquireVsCodeApi();let isThinking=false;let currentPlan=[];const messageInput=document.getElementById('messageInput');
                messageInput.addEventListener('input',function(){this.style.height='auto';this.style.height=this.scrollHeight+'px';});
                messageInput.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}});
                function sendMessage(){const input=document.getElementById('messageInput');const message=input.value.trim();if(!message||isThinking)return;vscode.postMessage({type:'sendMessage',message:message});input.value='';input.style.height='auto';}
                function submitReview(action){const feedback=document.getElementById('reviewFeedback').value.trim();vscode.postMessage({type:'submitReview',feedback:feedback,action:action});document.getElementById('reviewPanel').classList.remove('active');document.getElementById('reviewFeedback').value='';}
                function openFile(filePath){vscode.postMessage({type:'openFile',filePath:filePath});}
                function updateProgressList(currentStep,plan){const progressList=document.getElementById('progressList');const progressSteps=document.getElementById('progressSteps');if(!plan||plan.length===0){progressList.classList.remove('active');return;}currentPlan=plan;progressSteps.innerHTML='';plan.forEach((step,index)=>{const stepDiv=document.createElement('div');stepDiv.className='progress-step';const instruction=step.instruction||step.task||'Step '+(index+1);if(index<currentStep){stepDiv.classList.add('completed');stepDiv.innerHTML='<span class=\"step-icon\">✅</span><span class=\"step-text\">'+instruction+'</span>';}else if(index===currentStep){stepDiv.classList.add('current');stepDiv.innerHTML='<span class=\"step-icon\">⏳</span><span class=\"step-text\">'+instruction+'</span>';}else{stepDiv.innerHTML='<span class=\"step-icon\">⭕</span><span class=\"step-text\">'+instruction+'</span>';}progressSteps.appendChild(stepDiv);});progressList.classList.add('active');}
                function clearProgressList(){document.getElementById('progressList').classList.remove('active');currentPlan=[];}
                window.addEventListener('message',event=>{const message=event.data;switch(message.type){case 'addMessage':addMessage(message.role,message.content);break;case 'setThinking':isThinking=message.thinking;document.getElementById('thinking').classList.toggle('active',message.thinking);document.getElementById('sendButton').disabled=message.thinking;break;case 'stepUpdate':updateProgressList(message.step,message.plan);break;case 'reviewRequired':showReviewPanel(message.plan,message.files);break;case 'workflowComplete':addMessage('assistant',\`✅ Workflow complete! Generated \${message.files.length} files.\`);if(currentPlan.length>0){updateProgressList(currentPlan.length,currentPlan);}break;case 'error':addMessage('assistant',\`❌ Error: \${message.message}\`);clearProgressList();break;}});
                function addMessage(role,content){const messagesDiv=document.getElementById('messages');const emptyState=messagesDiv.querySelector('.empty-state');if(emptyState)emptyState.remove();const messageDiv=document.createElement('div');messageDiv.className='message '+role;messageDiv.innerHTML=\`<div class="role">\${role==='user'?'You':'Agentic IDE'}</div><div class="content">\${content}</div>\`;messagesDiv.appendChild(messageDiv);messagesDiv.scrollTop=messagesDiv.scrollHeight;}
                function showReviewPanel(plan,files){const reviewPanel=document.getElementById('reviewPanel');const filesDiv=document.getElementById('reviewFiles');filesDiv.innerHTML='<h4>Generated Files:</h4>';files.forEach(file=>{const fileItem=document.createElement('div');fileItem.className='file-item';fileItem.textContent='✓ '+file;fileItem.onclick=()=>openFile(file);filesDiv.appendChild(fileItem);});reviewPanel.classList.add('active');}
            </script>
        </body>
        </html>`;
    }
}