import axios, { AxiosInstance } from 'axios';
import WebSocket from 'ws';

export interface WorkflowSession {
    session_id: string;
    status: string;
    message: string;
}

export interface WorkflowStatus {
    session_id: string;
    status: string;
    current_step: number;
    total_steps: number;
    generated_files: string[];
    needs_review: boolean;
    plan: any[];
}

export interface ReviewResponse {
    session_id: string;
    feedback: string;
    action: string;
}

export interface WebSocketCallbacks {
    onStepUpdate?: (data: any) => void;
    onReviewRequired?: (data: any) => void;
    onComplete?: (data: any) => void;
    onError?: (error: any) => void;
}

export class BackendClient {
    private api: AxiosInstance;
    private baseUrl: string;

    constructor(baseUrl: string) {
        console.log('=== BackendClient Constructor ===');
        console.log('Base URL provided:', baseUrl);
        
        this.baseUrl = baseUrl;
        this.api = axios.create({
            baseURL: baseUrl,
            timeout: 30000,
        });
        
        console.log('✅ Axios instance created');
        console.log('   - baseURL:', baseUrl);
        console.log('   - timeout:', 30000);
        console.log('===================================');
    }

    async startWorkflow(request: string, projectPath: string): Promise<WorkflowSession> {
        console.log('=== startWorkflow called ===');
        console.log('Request:', request);
        console.log('Project path:', projectPath);
        console.log('Endpoint:', '/workflow/start');
        console.log('Full URL:', `${this.baseUrl}/workflow/start`);
        
        try {
            console.log('📤 Making POST request...');
            
            const response = await this.api.post('/workflow/start', {
                request,
                project_path: projectPath
            });
            
            console.log('✅ Response received!');
            console.log('   - Status:', response.status, response.statusText);
            console.log('   - Data:', response.data);
            console.log('============================');
            
            return response.data;
        } catch (error: any) {
            console.error('❌ ERROR in startWorkflow ===');
            console.error('Error type:', error.constructor.name);
            console.error('Error code:', error.code);
            console.error('Error message:', error.message);
            
            if (error.response) {
                console.error('Response error:');
                console.error('   - Status:', error.response.status);
                console.error('   - Data:', error.response.data);
                console.error('   - Headers:', error.response.headers);
            } else if (error.request) {
                console.error('Request made but no response received');
                console.error('   - Request:', error.request);
            } else {
                console.error('Error setting up request:', error.message);
            }
            
            console.error('Config:');
            console.error('   - URL:', error.config?.url);
            console.error('   - Base URL:', error.config?.baseURL);
            console.error('   - Method:', error.config?.method);
            console.error('Full error object:', error);
            console.error('==============================');
            
            throw error;
        }
    }

    async getStatus(sessionId: string): Promise<WorkflowStatus> {
        console.log('=== getStatus called ===');
        console.log('Session ID:', sessionId);
        console.log('Full URL:', `${this.baseUrl}/workflow/status/${sessionId}`);
        
        try {
            const response = await this.api.get(`/workflow/status/${sessionId}`);
            console.log('✅ Status response:', response.data);
            return response.data;
        } catch (error: any) {
            console.error('❌ ERROR in getStatus:', error);
            throw error;
        }
    }

    async submitReview(sessionId: string, feedback: string, action: string): Promise<void> {
        console.log('=== submitReview called ===');
        console.log('Session ID:', sessionId);
        console.log('Action:', action);
        console.log('Feedback length:', feedback.length);
        console.log('Full URL:', `${this.baseUrl}/workflow/review`);
        
        try {
            await this.api.post('/workflow/review', {
                session_id: sessionId,
                feedback,
                action
            });
            console.log('✅ Review submitted successfully');
        } catch (error: any) {
            console.error('❌ ERROR in submitReview:', error);
            throw error;
        }
    }

    async connectWebSocket(sessionId: string, callbacks: WebSocketCallbacks): Promise<void> {
        console.log('=== connectWebSocket called ===');
        console.log('Session ID:', sessionId);
        console.log('Base URL:', this.baseUrl);
        
        return new Promise((resolve, reject) => {
            // Fixed: Use regex with anchor to properly replace protocol
            const wsUrl = this.baseUrl.replace(/^http/, 'ws');
            const fullWsUrl = `${wsUrl}/ws/${sessionId}`;
            
            console.log('WebSocket URL calculated:');
            console.log('   - Original:', this.baseUrl);
            console.log('   - After replace:', wsUrl);
            console.log('   - Full WS URL:', fullWsUrl);
            
            console.log('🔌 Creating WebSocket connection...');
            const ws = new WebSocket(fullWsUrl);

            // Added: Connection open handler
            ws.on('open', () => {
                console.log('✅ WebSocket connection established successfully!');
            });

            ws.on('message', (data: WebSocket.Data) => {
                console.log('📨 WebSocket message received');
                console.log('   - Raw data:', data.toString());
                
                try {
                    const message = JSON.parse(data.toString());
                    console.log('   - Parsed message:', message);
                    console.log('   - Message type:', message.type);

                    switch (message.type) {
                        case 'step_update':
                            console.log('→ Handling step_update');
                            callbacks.onStepUpdate?.(message);
                            break;
                        case 'review_required':
                            console.log('→ Handling review_required');
                            callbacks.onReviewRequired?.(message);
                            console.log('🔒 Closing WebSocket (review required)');
                            ws.close();
                            resolve();
                            break;
                        case 'workflow_complete':
                            console.log('→ Handling workflow_complete');
                            callbacks.onComplete?.(message);
                            console.log('🔒 Closing WebSocket (workflow complete)');
                            ws.close();
                            resolve();
                            break;
                        case 'error':
                            console.error('→ Handling error message:', message);
                            callbacks.onError?.(message);
                            console.log('🔒 Closing WebSocket (error)');
                            ws.close();
                            reject(new Error(message.message));
                            break;
                        default:
                            console.warn('⚠️  Unknown message type:', message.type);
                    }
                } catch (parseError) {
                    console.error('❌ Failed to parse WebSocket message:', parseError);
                }
            });

            ws.on('error', (error) => {
                console.error('❌ WebSocket error occurred:');
                console.error('   - Error:', error);
                console.error('   - Error message:', error.message);
                callbacks.onError?.(error);
                reject(error);
            });

            ws.on('close', (code, reason) => {
                console.log('🔌 WebSocket connection closed');
                console.log('   - Code:', code);
                console.log('   - Reason:', reason.toString());
            });
        });
    }
}