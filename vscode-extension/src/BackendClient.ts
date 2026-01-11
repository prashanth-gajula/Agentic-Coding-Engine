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
        this.baseUrl = baseUrl;
        this.api = axios.create({
            baseURL: baseUrl,
            timeout: 30000,
        });
    }

    async startWorkflow(request: string, projectPath: string): Promise<WorkflowSession> {
        const response = await this.api.post('/workflow/start', {
            request,
            project_path: projectPath
        });
        return response.data;
    }

    async getStatus(sessionId: string): Promise<WorkflowStatus> {
        const response = await this.api.get(`/workflow/status/${sessionId}`);
        return response.data;
    }

    async submitReview(sessionId: string, feedback: string, action: string): Promise<void> {
        await this.api.post('/workflow/review', {
            session_id: sessionId,
            feedback,
            action
        });
    }

    async connectWebSocket(sessionId: string, callbacks: WebSocketCallbacks): Promise<void> {
        return new Promise((resolve, reject) => {
            // Fixed: Use regex with anchor to properly replace protocol
            const wsUrl = this.baseUrl.replace(/^http/, 'ws');
            const ws = new WebSocket(`${wsUrl}/ws/${sessionId}`);

            // Added: Connection open handler
            ws.on('open', () => {
                console.log('WebSocket connection established');
            });

            ws.on('message', (data: WebSocket.Data) => {
                const message = JSON.parse(data.toString());

                switch (message.type) {
                    case 'step_update':
                        callbacks.onStepUpdate?.(message);
                        break;
                    case 'review_required':
                        callbacks.onReviewRequired?.(message);
                        // Close WebSocket when review is required
                        ws.close();
                        resolve();
                        break;
                    case 'workflow_complete':
                        callbacks.onComplete?.(message);
                        ws.close();
                        resolve();
                        break;
                    case 'error':
                        callbacks.onError?.(message);
                        ws.close();
                        reject(new Error(message.message));
                        break;
                }
            });

            ws.on('error', (error) => {
                callbacks.onError?.(error);
                reject(error);
            });

            ws.on('close', () => {
                console.log('WebSocket connection closed');
            });
        });
    }
}