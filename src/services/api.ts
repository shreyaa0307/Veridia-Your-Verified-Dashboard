
// Default to backend on http://127.0.0.1:8000 or VITE_API_BASE_URL
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';


export interface UploadResponse {
  file_id: string;
  filename: string;
  file_path: string;
  message: string;
}

export interface DashboardGenerationResponse {
  dashboard_id: string;
  status: string;
  message: string;
}

export interface DashboardStatus {
  status: string;
  output_file?: string;
  dashboard_dir?: string;
  error?: string;
  running?: boolean;
  port?: number;
  process?: number;
  current_stage?: string;
  stage_progress?: number;
  stage_note?: string;
}

export interface DashboardRunResponse {
  dashboard_id: string;
  status: string;
  url: string;
  port: number;
}

export interface ChatEditResponse {
  dashboard_id: string;
  status: string;
  url: string;
  port: number;
  code: string;
}

export interface DashboardErrorResponse {
  dashboard_id: string;
  error: string;
  status: string;
}

export interface PipelineStage {
  stage: string;
  description: string;
  progress: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    stage: "stage_1",
    description: "Analyzing your dataset comprehensively",
    progress: 0,
    status: 'pending'
  },
  {
    stage: "stage_2", 
    description: "Searching for similar visualization examples",
    progress: 0,
    status: 'pending'
  },
  {
    stage: "stage_3",
    description: "Designing your dashboard layout",
    progress: 0,
    status: 'pending'
  },
  {
    stage: "stage_4",
    description: "Generating interactive visualization code",
    progress: 0,
    status: 'pending'
  },
  {
    stage: "stage_5",
    description: "Optimizing code for best performance",
    progress: 0,
    status: 'pending'
  },
  {
    stage: "stage_6",
    description: "Testing and correcting any errors",
    progress: 0,
    status: 'pending'
  }
];

class ApiService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async uploadDataset(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/upload-dataset`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Upload failed! status: ${response.status}`);
    }

    return response.json();
  }

  async generateDashboard(
    fileId: string,
    userPrompt: string
  ): Promise<DashboardGenerationResponse> {
    return this.request<DashboardGenerationResponse>('/generate-dashboard', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        file_id: fileId,
        user_prompt: userPrompt,
      }),
    });
  }

  async getDashboardStatus(dashboardId: string): Promise<DashboardStatus> {
    return this.request<DashboardStatus>(`/dashboard-status/${dashboardId}`);
  }

  async runDashboard(dashboardId: string): Promise<DashboardRunResponse> {
    return this.request<DashboardRunResponse>(`/run-dashboard/${dashboardId}`, {
      method: 'POST',
    });
  }

  async fixDashboard(dashboardId: string): Promise<DashboardRunResponse> {
    return this.request<DashboardRunResponse>(`/fix-dashboard/${dashboardId}`, {
      method: 'POST',
    });
  }

  async chatEdit(dashboardId: string, message: string): Promise<ChatEditResponse> {
    return this.request<ChatEditResponse>(`/chat-edit/${dashboardId}`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  }

  async getDashboardError(dashboardId: string): Promise<DashboardErrorResponse> {
    return this.request<DashboardErrorResponse>(`/dashboard-error/${dashboardId}`);
  }

  async stopDashboard(dashboardId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/stop-dashboard/${dashboardId}`);
  }

  async getSampleDataset(filename: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/data/${encodeURIComponent(filename)}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Failed to fetch dataset: ${response.status}`);
    }
    return response.blob();
  }

  async downloadDashboard(dashboardId: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/download-dashboard/${dashboardId}`);
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Download failed! status: ${response.status}`);
    }

    return response.blob();
  }

  async updateCodeAndRun(dashboardId: string, code: string): Promise<ChatEditResponse> {
    return this.request<ChatEditResponse>(`/update-code/${dashboardId}`, {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  }

  // Polling function for dashboard status
  async pollDashboardStatus(
    dashboardId: string,
    onUpdate: (status: DashboardStatus) => void,
    onComplete: (status: DashboardStatus) => void,
    onError: (error: string) => void
  ) {
    const poll = async () => {
      try {
        const status = await this.getDashboardStatus(dashboardId);
        onUpdate(status);

        if (status.status === 'completed') {
          onComplete(status);
        } else if (status.status === 'failed') {
          onError(status.error || 'Generation failed');
        } else {
          // Continue polling
          setTimeout(poll, 2000);
        }
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Polling failed');
      }
    };

    poll();
  }
}

export const apiService = new ApiService(); 