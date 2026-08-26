import React, { useState, useRef, useCallback } from 'react';
import { Upload, FileText, Sparkles, Play, CheckCircle, Github, Heart, BarChart3, Database, Download, Eye, Code, StopCircle, Loader2, Clock, Zap, ChevronRight, Copy, Check, Send, Bot } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import { apiService, DashboardStatus, DashboardRunResponse, PIPELINE_STAGES, PipelineStage } from '@/services/api';

// Import generated chart examples and logo
import chartExample1 from '@/assets/chart-example-1.jpg';
import chartExample2 from '@/assets/chart-example-2.jpg';
import chartExample3 from '@/assets/chart-example-3.jpg';
import vizAiLogo from '@/assets/viz-ai-logo.png';
import VideoInspirationGallery from '@/components/ui/videoInspirationGallery';

const DataVisualizationAgent = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [filePreview, setFilePreview] = useState<string>('');
  const [fileId, setFileId] = useState<string>('');
  const [dashboardId, setDashboardId] = useState<string>('');
  const [dashboardStatus, setDashboardStatus] = useState<DashboardStatus | null>(null);
  const [dashboardUrl, setDashboardUrl] = useState<string>('');
  const [isDashboardRunning, setIsDashboardRunning] = useState(false);
  const [generatedCode, setGeneratedCode] = useState<string>('');
  const [pipelineStages, setPipelineStages] = useState<PipelineStage[]>(PIPELINE_STAGES);
  const [currentStage, setCurrentStage] = useState<string>('');
  const [codeCopied, setCodeCopied] = useState(false);
  const lastStageNotifiedRef = useRef<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<HTMLElement | null>(null);
  const [chatMessage, setChatMessage] = useState<string>('');
  const [isChatSending, setIsChatSending] = useState<boolean>(false);
  const { toast } = useToast();
  // Right-side sidebar state
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);
  const [activeSidebarTab, setActiveSidebarTab] = useState<'preview' | 'code'>('preview');
  const [isCodeLoading, setIsCodeLoading] = useState<boolean>(false);
  const [isEditingCode, setIsEditingCode] = useState<boolean>(false);
  const [editedCode, setEditedCode] = useState<string>('');
  const [isRerunning, setIsRerunning] = useState<boolean>(false);
  // Persistent runtime error from Dash app launch
  const [runtimeError, setRuntimeError] = useState<string>('');
  // Short-term error polling timer
  const errorPollRef = useRef<number | null>(null);

  const fetchLatestError = useCallback(async (did: string) => {
    try {
      const er = await apiService.getDashboardError(did);
      setRuntimeError(er.error || '');
    } catch {
      // ignore
    }
  }, []);

  const startErrorPolling = useCallback((did: string, durationMs: number = 5000, intervalMs: number = 1000) => {
    const start = Date.now();
    if (errorPollRef.current) {
      window.clearInterval(errorPollRef.current);
      errorPollRef.current = null;
    }
    errorPollRef.current = window.setInterval(async () => {
      if (Date.now() - start > durationMs) {
        if (errorPollRef.current) {
          window.clearInterval(errorPollRef.current);
          errorPollRef.current = null;
        }
        return;
      }
      await fetchLatestError(did);
    }, intervalMs);
  }, [fetchLatestError]);

  const examplePrompts = [
    {
      text: "Create an animated line chart showing COVID-19 cases by country over time with interactive hover details",
      image: chartExample1,
      category: "Time Series"
    },
    {
      text: "Build a 3D scatterplot of income vs life expectancy by country with population as bubble size",
      image: chartExample2,
      category: "Correlation"
    },
    {
      text: "Generate an interactive world map showing climate data with color-coded regions and zoom functionality",
      image: chartExample3,
      category: "Geographic"
    }
  ];

  const processSteps = [
    {
      id: 1,
      title: "Upload Your Dataset",
      description: "Simply drag & drop your CSV file or click to browse. Our AI will automatically analyze your data structure and suggest the best visualization approaches for your specific dataset.",
      icon: Database,
      color: "from-blue-500/20 to-cyan-500/20",
      borderColor: "border-blue-500/30",
      iconColor: "text-blue-400",
      detail: "Supports CSV files up to 100MB with automatic data type detection and validation"
    },
    {
      id: 2,
      title: "Get Your Interactive Dashboard",
      description: "Receive a professional Tableau-style dashboard with animated charts, dynamic filters, and drill-down capabilities. Every visualization is interactive and updates in real-time as you explore your data.",
      icon: BarChart3,
      color: "from-purple-500/20 to-pink-500/20",
      borderColor: "border-purple-500/30",
      iconColor: "text-purple-400",
      detail: "Includes hover tooltips, zoom functionality, and cross-filtering between charts"
    },
    {
      id: 3,
      title: "Customize & Edit Code",
      description: "Access the complete Python code powering your dashboard. Edit, enhance, and rerun it unlimited times. Add new visualizations, modify styling, or integrate additional data sources.",
      icon: Code,
      color: "from-green-500/20 to-emerald-500/20",
      borderColor: "border-green-500/30",
      iconColor: "text-green-400",
      detail: "Built with Plotly & Dash - industry-standard libraries for production dashboards"
    },
    {
      id: 4,
      title: "AI-Powered Refinements",
      description: "Chat with our AI agent to modify your dashboard instantly. Add new plots, remove elements, change colors, or implement advanced features - all through natural language commands.",
      icon: Bot,
      color: "from-orange-500/20 to-red-500/20",
      borderColor: "border-orange-500/30",
      iconColor: "text-orange-400",
      detail: "Supports complex requests like 'add a correlation heatmap' or 'change to dark theme'"
    }
  ];

  const previewFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      const preview = content.length > 200 ? content.substring(0, 200) + '...' : content;
      setFilePreview(preview);
    };
    reader.readAsText(file);
  }, []);

  const handleFileUpload = useCallback(async (file: File) => {
    try {
      setIsLoading(true);

      // Upload file to backend
      const uploadResponse = await apiService.uploadDataset(file);
      setFileId(uploadResponse.file_id);
      setSelectedFile(file);
      previewFile(file);

      toast({
        title: "File uploaded successfully!",
        description: `${file.name} is ready for processing.`,
      });
    } catch (error) {
      toast({
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Failed to upload file",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  }, [previewFile, toast]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    const dataFile = files.find(file =>
      file.type === 'text/csv' ||
      file.name.endsWith('.csv')
    );

    if (dataFile) {
      await handleFileUpload(dataFile);
    } else {
      toast({
        title: "Invalid file type",
        description: "Please upload a CSV file.",
        variant: "destructive"
      });
    }
  }, [handleFileUpload, toast]);

  // Auto-indent for the editor: keep same leading spaces as current line on Enter
  const handleEditorKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
    e.preventDefault();
    const ta = e.currentTarget;
    const value = ta.value;
    const start = ta.selectionStart ?? 0;
    const end = ta.selectionEnd ?? start;
    // Find the start of the current line
    const lineStart = value.lastIndexOf('\n', Math.max(0, start - 1)) + 1;
    const line = value.slice(lineStart, start);
    const indentMatch = line.match(/^[\t ]*/);
    const indent = indentMatch ? indentMatch[0] : '';
    const insertion = '\n' + indent;
    const newValue = value.slice(0, start) + insertion + value.slice(end);
    const newCaret = start + insertion.length;
    // Update state and caret
    setEditedCode(newValue);
    // Defer caret placement until after React state update
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = newCaret;
    });
  };

  // Handle tab switching with lazy code load
  const handleSidebarTabChange = async (tab: 'preview' | 'code') => {
    setActiveSidebarTab(tab);
    if (tab === 'code' && !generatedCode && dashboardId) {
      try {
        setIsCodeLoading(true);
        const blob = await apiService.downloadDashboard(dashboardId);
        const text = await blob.text();
        setGeneratedCode(text);
        setEditedCode(text);
      } catch (error) {
        toast({
          title: 'Failed to load code',
          description: error instanceof Error ? error.message : 'Unable to fetch code',
          variant: 'destructive'
        });
      } finally {
        setIsCodeLoading(false);
      }
    } else if (tab === 'code' && generatedCode && !isEditingCode) {
      // Keep user edits if in editing mode; otherwise sync editor to latest code
      setEditedCode(generatedCode);
    }
  };

  const handleStartEditing = () => {
    setIsEditingCode(true);
    setEditedCode(generatedCode || editedCode);
  };

  const handleCancelEditing = () => {
    setIsEditingCode(false);
    setEditedCode(generatedCode); // revert
  };

  const handleRerunCode = async () => {
    if (!dashboardId) return;
    try {
      setIsRerunning(true);
      const res = await apiService.updateCodeAndRun(dashboardId, isEditingCode ? editedCode : (generatedCode || ''));
      // Update URL and code, mark running again
      setDashboardUrl(res.url);
      setIsDashboardRunning(true);
      setRuntimeError('');
      if (res.code) {
        setGeneratedCode(res.code);
        setEditedCode(res.code);
      }
      toast({ title: 'Dashboard reloaded', description: 'Your edits are now live.' });
      setActiveSidebarTab('preview');
      setIsSidebarOpen(true);
      setIsEditingCode(false);
    } catch (error) {
      toast({
        title: 'Failed to rerun code',
        description: error instanceof Error ? error.message : 'See logs in dashboard directory',
        variant: 'destructive'
      });
      // Always fetch latest detailed error and start short polling
      if (dashboardId) {
        await fetchLatestError(dashboardId);
        startErrorPolling(dashboardId);
      }
    } finally {
      setIsRerunning(false);
    }
  };

  // Apply chat-driven changes to the generated dashboard
  const handleChatSend = async () => {
    if (!dashboardId || !chatMessage.trim()) return;
    setIsChatSending(true);
    try {
      const res = await apiService.chatEdit(dashboardId, chatMessage.trim());
      // Update URL and code, mark running again
      setDashboardUrl(res.url);
      setIsDashboardRunning(true);
      setGeneratedCode(res.code || '');
      if (res.code) setEditedCode(res.code);
      setRuntimeError('');
      setActiveSidebarTab('preview');
      setIsSidebarOpen(true);
      setChatMessage('');
      toast({ title: 'Applied changes', description: 'Dashboard updated and reloaded.' });
      // Open sidebar to preview by default after edit
      setActiveSidebarTab('preview');
      setIsSidebarOpen(true);
    } catch (error) {
      toast({
        title: 'Failed to apply change',
        description: error instanceof Error ? error.message : 'Unable to update dashboard',
        variant: 'destructive'
      });
      if (dashboardId) {
        await fetchLatestError(dashboardId);
        startErrorPolling(dashboardId);
      }
    } finally {
      setIsChatSending(false);
    }
  };

  const handleAttemptFix = async () => {
    if (!dashboardId) return;
    try {
      const fixResponse = await apiService.fixDashboard(dashboardId);
      setDashboardUrl(fixResponse.url);
      setIsDashboardRunning(true);
      setActiveSidebarTab('preview');
      setIsSidebarOpen(true);
      setRuntimeError('');
      toast({ title: 'Auto-fixed and running', description: `Dashboard recovered. URL: ${fixResponse.url}` });
    } catch (fixErr) {
      // Fetch detailed error and display; start polling briefly
      await fetchLatestError(dashboardId);
      startErrorPolling(dashboardId);
      toast({ title: 'Auto-fix failed', description: fixErr instanceof Error ? fixErr.message : 'See error panel below', variant: 'destructive' });
    }
  };

  const handleStartDashboard = async () => {
    if (!dashboardId) return;
    setIsLoading(true);
    try {
      const runResponse = await apiService.runDashboard(dashboardId);
      setDashboardUrl(runResponse.url);
      setIsDashboardRunning(true);
      setRuntimeError('');
      setActiveSidebarTab('preview');
      setIsSidebarOpen(true);
      toast({
        title: "Dashboard is running!",
        description: `Access it at: ${runResponse.url}`,
      });
    } catch (error) {
      // Attempt auto-fix and rerun
      try {
        const fixResponse = await apiService.fixDashboard(dashboardId);
        setDashboardUrl(fixResponse.url);
        setIsDashboardRunning(true);
        setRuntimeError('');
        setActiveSidebarTab('preview');
        setIsSidebarOpen(true);
        toast({
          title: "Auto-fixed and running",
          description: `Dashboard recovered. URL: ${fixResponse.url}`,
        });
      } catch (fixErr) {
        // Pull latest error from backend error endpoint and poll briefly
        await fetchLatestError(dashboardId);
        startErrorPolling(dashboardId);
        toast({
          title: "Failed to start dashboard",
          description: fixErr instanceof Error ? fixErr.message : (error instanceof Error ? error.message : 'Unknown error'),
          variant: 'destructive'
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Cleanup error polling on unmount
  React.useEffect(() => {
    return () => {
      if (errorPollRef.current) {
        window.clearInterval(errorPollRef.current);
        errorPollRef.current = null;
      }
    };
  }, []);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await handleFileUpload(file);
    }
  };

  const handleExamplePrompt = (exampleText: string) => {
    setPrompt(exampleText);
    document.getElementById('prompt-textarea')?.focus();
  };

  // When user selects a template from the gallery, auto-download dataset and upload
  const handleUseTemplate = async ({ prompt: tplPrompt, dataset }: { prompt: string; dataset: string }) => {
    try {
      // Set prompt immediately for UX
      setPrompt(tplPrompt);

      // Fetch dataset from backend sample datasets via apiService
      const blob = await apiService.getSampleDataset(dataset);
      const file = new File([blob], dataset, { type: 'text/csv' });

      // Upload via existing flow
      await handleFileUpload(file);

      toast({ title: 'Template loaded', description: `${dataset} uploaded and prompt filled.` });
    } catch (e) {
      toast({
        title: 'Failed to load template',
        description: e instanceof Error ? e.message : 'Could not download or upload dataset',
        variant: 'destructive',
      });
    }
  };

  const handleSubmit = async () => {
    if (!fileId || !prompt.trim()) {
      toast({
        title: "Missing information",
        description: "Please upload a dataset and provide a description.",
        variant: "destructive"
      });
      return;
    }

    setIsLoading(true);

    try {
      // Generate dashboard
      const generationResponse = await apiService.generateDashboard(fileId, prompt);
      setDashboardId(generationResponse.dashboard_id);

      toast({
        title: "Dashboard generation started!",
        description: "This may take a few minutes. We'll notify you when it's ready.",
      });

      // Start polling for status
      apiService.pollDashboardStatus(
        generationResponse.dashboard_id,
        (status) => {
          setDashboardStatus(status);
          // Update pipeline stage visualization based on current stage
          if (status.current_stage) {
            const idx = PIPELINE_STAGES.findIndex(s => s.stage === status.current_stage);
            if (idx !== -1) {
              setPipelineStages(PIPELINE_STAGES.map((s, i) => ({
                ...s,
                status: i < idx ? 'completed' : i === idx && status.status === 'generating' ? 'running' : 'pending',
                progress: i === idx && (status.stage_progress ?? 0) > 0 ? (status.stage_progress as number) : (i < idx ? 100 : 0),
              })));
            }
          }
          // Notify only on stage changes to avoid spam
          if (status.current_stage && lastStageNotifiedRef.current !== status.current_stage) {
            lastStageNotifiedRef.current = status.current_stage;
            setCurrentStage(status.current_stage);
            const stageDef = PIPELINE_STAGES.find(s => s.stage === status.current_stage);
            if (status.status === 'generating' && stageDef) {
              toast({
                title: `Stage: ${stageDef.description}`,
                description: status.stage_note ? status.stage_note : `Progress: ${status.stage_progress ?? 0}%`,
              });
            }
          }
        },
        async (status) => {
          setDashboardStatus(status);
          setIsLoading(false);

          toast({
            title: "Dashboard generated!",
            description: "Your interactive visualization is ready!",
          });

          // Try to run the dashboard
          try {
            const runResponse = await apiService.runDashboard(generationResponse.dashboard_id);
            setDashboardUrl(runResponse.url);
            setIsDashboardRunning(true);
            setActiveSidebarTab('preview');
            setIsSidebarOpen(true);

            toast({
              title: "Dashboard is running!",
              description: `Access it at: ${runResponse.url}`,
            });
          } catch (error) {
            // If initial run fails, call auto-fix and retry once
            try {
              const fixResponse = await apiService.fixDashboard(generationResponse.dashboard_id);
              setDashboardUrl(fixResponse.url);
              setIsDashboardRunning(true);
              setActiveSidebarTab('preview');
              setIsSidebarOpen(true);
              toast({
                title: "Auto-fixed and running",
                description: `Dashboard recovered. URL: ${fixResponse.url}`,
              });
            } catch (fixErr) {
              // Fetch latest error and poll briefly so error panel reflects real logs
              await fetchLatestError(generationResponse.dashboard_id);
              startErrorPolling(generationResponse.dashboard_id);
              toast({
                title: "Dashboard generated but failed to start",
                description: fixErr instanceof Error ? fixErr.message : 'Auto-fix also failed',
                variant: "destructive"
              });
            }
          }
        },
        (error) => {
          setIsLoading(false);
          toast({
            title: "Generation failed",
            description: error,
            variant: "destructive"
          });
        }
      );

    } catch (error) {
      setIsLoading(false);
      toast({
        title: "Generation failed",
        description: error instanceof Error ? error.message : "Failed to start generation",
        variant: "destructive"
      });
    }
  };

  const handleDownloadCode = async () => {
    if (!dashboardId) return;

    try {
      const blob = await apiService.downloadDashboard(dashboardId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dashboard_${dashboardId}.py`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast({
        title: "Code downloaded!",
        description: "You can now run the dashboard locally.",
      });
    } catch (error) {
      toast({
        title: "Download failed",
        description: error instanceof Error ? error.message : "Failed to download code",
        variant: "destructive"
      });
    }
  };

  const handleStopDashboard = async () => {
    if (!dashboardId) return;

    try {
      await apiService.stopDashboard(dashboardId);
      setIsDashboardRunning(false);
      setDashboardUrl('');

      toast({
        title: "Dashboard stopped",
        description: "The dashboard has been stopped.",
      });
    } catch (error) {
      toast({
        title: "Failed to stop dashboard",
        description: error instanceof Error ? error.message : "Failed to stop dashboard",
        variant: "destructive"
      });
    }
  };

  const handleViewCode = async () => {
    if (!dashboardId) return;

    try {
      const blob = await apiService.downloadDashboard(dashboardId);
      const text = await blob.text();
      setGeneratedCode(text);
      setEditedCode(text);
      setActiveSidebarTab('code');
      setIsSidebarOpen(true);

      toast({
        title: "Code loaded!",
        description: "View the generated Python code in the sidebar.",
      });
    } catch (error) {
      toast({
        title: "Failed to load code",
        description: error instanceof Error ? error.message : "Failed to load code",
        variant: "destructive"
      });
    }
  };

  const handleCopyCode = async () => {
    if (!generatedCode) return;

    try {
      await navigator.clipboard.writeText(generatedCode);
      setCodeCopied(true);
      setTimeout(() => setCodeCopied(false), 2000);
      toast({
        title: "Code copied!",
        description: "Code has been copied to your clipboard.",
      });
    } catch (error) {
      toast({
        title: "Failed to copy",
        description: "Could not copy code to clipboard.",
        variant: "destructive"
      });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800">
      {/* Subtle Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl" />
        <div className="absolute top-3/4 right-1/4 w-80 h-80 bg-purple-500/5 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-3/4 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(71,85,105,0.1)_0%,transparent_50%)]" />
      </div>

      <div className="relative z-10">
        {/* Header Section */}
        <header className="text-center py-20 px-6">
          <div className="max-w-6xl mx-auto">
            {/* Logo and Brand */}
            <div className="flex items-center justify-center gap-4 mb-12">
              <div className="relative">
                <img src={vizAiLogo} alt="Veridia logo" className="w-20 h-20 drop-shadow-lg" decoding="async"/>
                <div className="absolute inset-0 bg-gradient-to-r from-blue-400/20 to-purple-400/20 rounded-full blur-xl" />
              </div>
              <div className="text-left">
                <h1 className="text-5xl md:text-7xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
                  Veridia
                </h1>
                <p className="text-sm text-slate-400 font-medium tracking-wide">
                  Your Verified Dashboard
                </p>
              </div>
            </div>

            {/* Main Headline */}
            <div className="mb-12">
              <h2 className="text-4xl md:text-6xl font-bold mb-6 text-white leading-tight">
                Transform Data Into{' '}
                <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  Professional Dashboards
                </span>
              </h2>

              <p className="text-xl md:text-2xl text-slate-300 mb-8 max-w-4xl mx-auto leading-relaxed">
                Create enterprise-grade, interactive dashboards from any dataset with just one prompt.{' '}
                <span className="text-cyan-400 font-semibold">No coding experience required.</span>
              </p>

              {/* Stats */}
              <div className="flex justify-center gap-8 mt-8 text-sm text-slate-400">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                  <span>Tableau-style Quality</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
                  <span>Production Ready</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-purple-400 rounded-full"></div>
                  <span>Fully Customizable</span>
                </div>
              </div>
            </div>

            {/* Process Steps */}
            <div className="mb-16">
              <h3 className="text-2xl md:text-3xl font-bold text-white mb-12">
                How It Works
              </h3>

              <div className="grid lg:grid-cols-4 md:grid-cols-2 gap-6 max-w-7xl mx-auto">
                {processSteps.map((step, index) => (
                  <div
                    key={step.id}
                    className={`relative group bg-gradient-to-br ${step.color} backdrop-blur-sm border ${step.borderColor} rounded-2xl p-8 hover:scale-105 transition-all duration-500 hover:shadow-2xl`}
                  >
                    {/* Step Number */}
                    <div className="absolute -top-4 -left-4 w-8 h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white text-sm font-bold shadow-lg">
                      {step.id}
                    </div>

                    {/* Icon */}
                    <div className={`w-16 h-16 rounded-xl bg-slate-800/50 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
                      <step.icon className={`w-8 h-8 ${step.iconColor}`} />
                    </div>

                    {/* Content */}
                    <h4 className="text-xl font-bold text-white mb-4 group-hover:text-cyan-300 transition-colors">
                      {step.title}
                    </h4>
                    
                    <p className="text-slate-300 text-sm leading-relaxed mb-4">
                      {step.description}
                    </p>

                    <div className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-3">
                      {step.detail}
                    </div>

                    {/* Connecting Line (except for last item) */}
                    {index < processSteps.length - 1 && (
                      <div className="hidden lg:block absolute top-1/2 -right-3 w-6 h-0.5 bg-gradient-to-r from-slate-600 to-transparent">
                        <ChevronRight className="absolute -right-2 -top-2 w-4 h-4 text-slate-500" />
                      </div>
                    )}

                    {/* Hover Glow Effect */}
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-blue-500/10 to-purple-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500 -z-10 blur-xl" />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap justify-center gap-6 mt-12">
              {[chartExample1, chartExample2, chartExample3].map((image, index) => (
                <div
                  key={index}
                  className="bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 p-2 hover:scale-105 transition-all duration-300 cursor-pointer animate-glow-pulse rounded-lg"
                  style={{ animationDelay: `${index * 0.5}s` }}
                >
                  <img
                    src={image}
                    alt={`Data visualization example ${index + 1}`}
                    loading="lazy"
                    decoding="async"
                    className="w-32 h-20 object-cover rounded-lg"
                  />
                </div>
              ))}
            </div>
          </div>
        </header>

        {/* Main Form Section */}
        <main className="max-w-6xl mx-auto px-6 pb-16">
          <div className="grid lg:grid-cols-2 gap-8 mb-16">
            {/* File Upload */}
            <Card className="bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 hover:border-slate-600/50 transition-all duration-300 p-8">
              <h2 className="text-2xl font-poppins font-semibold mb-6 flex items-center gap-3 text-slate-100">
                <Upload className="text-neon-blue" />
                Upload Your Dataset
              </h2>

              <div
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300 ${isDragOver
                  ? 'border-neon-cyan bg-neon-cyan/5'
                  : 'border-slate-600 hover:border-slate-500 bg-slate-700/20'
                  }`}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileSelect}
                  className="hidden"
                />

                {selectedFile ? (
                  <div className="space-y-4">
                    <CheckCircle className="w-12 h-12 text-neon-green mx-auto" />
                    <div>
                      <p className="text-lg font-semibold text-neon-green">{selectedFile.name}</p>
                      <div className="flex items-center justify-center gap-2 mt-2">
                        <Badge variant="secondary" className="text-xs">
                          CSV
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {(selectedFile.size / 1024).toFixed(1)} KB
                        </Badge>
                      </div>
                      {filePreview && (
                        <div className="mt-3 p-3 bg-slate-700/30 rounded border text-xs text-left max-h-20 overflow-y-auto">
                          <p className="text-slate-400 mb-1">Preview:</p>
                          <code className="text-xs text-slate-300">{filePreview}</code>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <Database className="w-12 h-12 text-slate-400 mx-auto" />
                    <div>
                      <p className="text-lg font-semibold text-slate-200">Drop your CSV dataset here</p>
                      <p className="text-sm text-slate-400">Or click to browse files</p>
                      <div className="flex items-center justify-center gap-2 mt-2">
                        <Badge variant="outline" className="text-xs">CSV Only</Badge>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </Card>

            {/* Prompt Input */}
            <Card className="bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 hover:border-slate-600/50 transition-all duration-300 p-8">
              <h2 className="text-2xl font-poppins font-semibold mb-6 flex items-center gap-3 text-slate-100">
                <Sparkles className="text-neon-purple" />
                Describe Your Visualization
              </h2>

              <div className="space-y-4">
                <Textarea
                  id="prompt-textarea"
                  placeholder="e.g., Create a Tableau-style dashboard showing sales performance by region with interactive filters, drill-down capabilities, and animated trend lines"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="min-h-32 bg-slate-700/30 border-slate-600 focus:border-neon-cyan focus:ring-neon-cyan/20 transition-all duration-300 text-slate-100 placeholder:text-slate-400"
                />
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400">
                    {prompt.length} / 500
                  </span>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <div className="w-2 h-2 bg-neon-purple rounded-full animate-pulse" />
                    AI-powered dashboard generation
                  </div>
                </div>
              </div>
            </Card>
          </div>

          {/* Generate Button & Stats */}
          <div className="text-center mb-16 space-y-6">
            <Button
              onClick={handleSubmit}
              disabled={isLoading || !fileId || !prompt.trim()}
              className="bg-gradient-to-r from-neon-blue to-neon-cyan hover:from-neon-blue/90 hover:to-neon-cyan/90 text-black font-poppins font-semibold text-lg px-12 py-4 rounded-xl shadow-lg hover:shadow-neon-blue/25 transition-all duration-300"
            >
              {isLoading ? (
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  {dashboardStatus?.status === 'generating' ? 'Generating Dashboard...' : 'Starting Generation...'}
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <BarChart3 className="w-5 h-5" />
                  Generate Interactive Dashboard
                </div>
              )}
            </Button>

            {/* Enhanced Stats */}
            <div className="flex items-center justify-center gap-8 text-sm">
              <div className="flex items-center gap-2 text-slate-300">
                <div className="w-2 h-2 bg-neon-green rounded-full animate-pulse" />
                <span>5-Stage AI Pipeline</span>
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <div className="w-2 h-2 bg-neon-blue rounded-full animate-pulse" />
                <span>Tableau-style Interface</span>
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <div className="w-2 h-2 bg-neon-purple rounded-full animate-pulse" />
                <span>Real-time Filtering</span>
              </div>
            </div>
          </div>

          {/* Chat Edit Panel - shown after generation or when running */}
          {(dashboardStatus?.status === 'completed' || isDashboardRunning) && (
            <Card className="bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 hover:border-slate-600/50 transition-all duration-300 p-8 mb-16">
              <h2 className="text-2xl font-poppins font-semibold mb-2 flex items-center gap-3 text-slate-100">
                <Send className="text-neon-purple" />
                Refine Your Dashboard
              </h2>
              <p className="text-slate-400 mb-4 text-sm">Describe incremental changes. We’ll minimally edit the running app and refresh the preview.</p>

              <div className="space-y-3">
                <Textarea
                  aria-label="Edit instructions"
                  placeholder="e.g., Add a date range slider; color the bars by category; make the map default to Europe"
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                  className="min-h-24 bg-slate-700/30 border-slate-600 focus:border-neon-purple focus:ring-neon-purple/20 text-slate-100"
                />
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    onClick={handleChatSend}
                    disabled={isChatSending || !chatMessage.trim() || !dashboardId}
                    aria-busy={isChatSending}
                    className="bg-gradient-to-r from-neon-purple to-neon-blue text-black"
                  >
                    {isChatSending ? (
                      <div className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin"/>Applying...</div>
                    ) : (
                      <div className="flex items-center gap-2"><Send className="w-4 h-4"/>Apply change</div>
                    )}
                  </Button>
                  {dashboardUrl && (
                    <a href={dashboardUrl} target="_blank" rel="noreferrer" className="text-neon-cyan text-sm underline">
                      Open updated dashboard →
                    </a>
                  )}
                  {generatedCode && (
                    <span className="text-xs text-slate-400">Updated code appears in the Generated Python Code section below.</span>
                  )}
                </div>
              </div>
            </Card>
          )}

          {/* Enhanced Dashboard Status & Controls */}
          {dashboardStatus && (
            <section className="mb-16">
              <div className="text-center mb-8">
                <h2 className="text-3xl font-poppins font-bold mb-2 flex items-center justify-center gap-3 text-slate-100">
                  <Zap className="text-neon-blue animate-pulse" />
                  AI Dashboard Pipeline
                </h2>
                <p className="text-slate-400">Watch your data transform in real-time</p>
              </div>

              <Card className="bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 hover:border-slate-600/50 transition-all duration-300 overflow-hidden">
                {/* Enhanced Status Header */}
                <div className="bg-gradient-to-r from-slate-800/60 to-slate-700/60 backdrop-blur-sm p-6 border-b border-slate-700/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="relative">
                        <div className={`w-4 h-4 rounded-full ${dashboardStatus.status === 'completed' ? 'bg-neon-green animate-pulse' :
                          dashboardStatus.status === 'generating' ? 'bg-neon-blue animate-pulse' :
                            dashboardStatus.status === 'failed' ? 'bg-red-500' : 'bg-slate-500'
                          }`} />
                        {dashboardStatus.status === 'generating' && (
                          <div className="absolute inset-0 bg-neon-blue rounded-full animate-ping opacity-75" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-lg capitalize text-slate-100">
                            {dashboardStatus.status === 'generating' ? 'Building Your Dashboard' :
                              dashboardStatus.status === 'completed' ? 'Dashboard Ready' :
                                dashboardStatus.status === 'failed' ? 'Generation Failed' : 'Processing'}
                          </span>
                          {dashboardStatus.status === 'generating' && (
                            <Badge variant="secondary" className="text-xs bg-neon-blue/20 text-neon-blue border-neon-blue/30">
                              Live
                            </Badge>
                          )}
                        </div>
                        {dashboardStatus.status === 'generating' && currentStage && (
                          <p className="text-sm text-slate-300 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Currently: {PIPELINE_STAGES.find(s => s.stage === currentStage)?.description || 'Processing...'}
                          </p>
                        )}
                      </div>
                    </div>

                    {dashboardStatus.status === 'completed' && (
                      <div className="flex gap-3">
                        <Button variant="outline" size="sm" onClick={handleViewCode} className="hover:border-neon-cyan bg-slate-800/50 border-slate-600 text-slate-200">
                          <Code className="w-4 h-4 mr-2" />
                          View Code
                        </Button>
                        <Button variant="outline" size="sm" onClick={handleDownloadCode} className="hover:border-neon-green bg-slate-800/50 border-slate-600 text-slate-200">
                          <Download className="w-4 h-4 mr-2" />
                          Download
                        </Button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="p-6 space-y-6">
                  {/* Enhanced Pipeline Progress */}
                  {dashboardStatus.status === 'generating' && (
                    <div className="space-y-6">
                      <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-slate-100">Generation Progress</h3>
                        <Badge variant="outline" className="text-xs">
                          {pipelineStages.filter(s => s.status === 'completed').length} / {pipelineStages.length} Stages
                        </Badge>
                      </div>

                      <div className="space-y-4">
                        {pipelineStages.map((stage, index) => (
                          <div key={stage.stage} className="relative">
                            <div className={`flex items-center gap-4 p-4 rounded-lg border transition-all duration-500 ${stage.status === 'completed' ? 'bg-neon-green/5 border-neon-green/20' :
                              stage.status === 'running' ? 'bg-neon-blue/5 border-neon-blue/20 shadow-lg' :
                                stage.status === 'failed' ? 'bg-red-500/5 border-red-500/20' :
                                  'bg-slate-800/20 border-slate-700/50'
                              }`}>
                              {/* Stage Icon */}
                              <div className={`relative w-10 h-10 rounded-full flex items-center justify-center font-semibold ${stage.status === 'completed' ? 'bg-neon-green text-black' :
                                stage.status === 'running' ? 'bg-neon-blue text-black' :
                                  stage.status === 'failed' ? 'bg-red-500 text-white' :
                                    'bg-slate-600 text-slate-300'
                                }`}>
                                {stage.status === 'running' ? (
                                  <Loader2 className="w-5 h-5 animate-spin" />
                                ) : stage.status === 'completed' ? (
                                  <CheckCircle className="w-5 h-5" />
                                ) : (
                                  <span className="text-sm">{index + 1}</span>
                                )}

                                {stage.status === 'running' && (
                                  <>
                                    <div className="absolute inset-0 bg-neon-blue rounded-full animate-ping opacity-30" />
                                    <div className="absolute inset-0 bg-neon-blue rounded-full animate-pulse opacity-50" />
                                  </>
                                )}
                              </div>

                              {/* Stage Content */}
                              <div className="flex-1">
                                <div className="flex items-center justify-between mb-1">
                                  <p className={`font-semibold ${stage.status === 'running' ? 'text-neon-blue' :
                                    stage.status === 'completed' ? 'text-neon-green' :
                                      stage.status === 'failed' ? 'text-red-500' :
                                        'text-slate-400'
                                    }`}>
                                    {stage.description}
                                  </p>

                                  {stage.status === 'running' && (
                                    <div className="flex items-center gap-2 text-sm text-neon-blue">
                                      <div className="w-2 h-2 bg-neon-blue rounded-full animate-pulse" />
                                      Processing...
                                    </div>
                                  )}

                                  {stage.status === 'completed' && (
                                    <div className="flex items-center gap-1 text-sm text-neon-green">
                                      <CheckCircle className="w-3 h-3" />
                                      Complete
                                    </div>
                                  )}
                                </div>

                                {/* Progress Bar for Running Stage */}
                                {stage.status === 'running' && (
                                  <div className="w-full bg-slate-700/30 rounded-full h-2 overflow-hidden">
                                    <div
                                      className="h-full bg-gradient-to-r from-neon-blue to-neon-cyan rounded-full animate-pulse transition-all duration-700"
                                      style={{ width: `${Math.max(10, Math.min(100, stage.progress || 0))}%` }}
                                    />
                                  </div>
                                )}
                              </div>

                              {/* Connection Line */}
                              {index < pipelineStages.length - 1 && (
                                <div className={`absolute left-9 top-16 w-0.5 h-6 ${stage.status === 'completed' ? 'bg-neon-green/30' :
                                  stage.status === 'running' ? 'bg-neon-blue/30' :
                                    'bg-slate-700/30'
                                  }`} />
                              )}
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Real-time Status */}
                      <div className="bg-slate-800/20 rounded-lg p-4 border border-dashed border-slate-700">
                        <div className="flex items-center gap-3 text-sm">
                          <div className="w-3 h-3 bg-neon-blue rounded-full animate-pulse" />
                          <span className="text-slate-300">
                            {dashboardStatus.stage_note || 'AI is analyzing your data and generating custom visualizations...'}
                          </span>
                          <div className="flex gap-1">
                            <div className="w-1 h-1 bg-neon-blue rounded-full animate-bounce" />
                            <div className="w-1 h-1 bg-neon-blue rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                            <div className="w-1 h-1 bg-neon-blue rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Enhanced Dashboard Controls */}
                  {dashboardStatus.status === 'completed' && (
                    <div className="space-y-4">
                      <h3 className="text-lg font-semibold flex items-center gap-2 text-slate-100">
                        <Play className="w-5 h-5 text-neon-green" />
                        Dashboard Controls
                      </h3>

                      {isDashboardRunning ? (
                        <div className="bg-gradient-to-r from-neon-green/10 to-emerald-500/10 p-4 rounded-lg border border-neon-green/20">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <div className="relative">
                                <div className="w-3 h-3 bg-neon-green rounded-full animate-pulse" />
                                <div className="absolute inset-0 bg-neon-green rounded-full animate-ping opacity-30" />
                              </div>
                              <div>
                                <span className="font-semibold text-neon-green">Dashboard Live</span>
                                <p className="text-sm text-slate-300">Your visualization is running and accessible</p>
                              </div>
                            </div>
                            <div className="flex gap-3">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => window.open(dashboardUrl, '_blank')}
                                className="hover:border-neon-green hover:text-neon-green bg-slate-800/50 border-slate-600"
                              >
                                <Eye className="w-4 h-4 mr-2" />
                                Open Dashboard
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handleStopDashboard}
                                className="hover:border-red-400 hover:text-red-400 bg-slate-800/50 border-slate-600"
                              >
                                <StopCircle className="w-4 h-4 mr-2" />
                                Stop
                              </Button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-slate-800/30 p-4 rounded-lg border border-dashed border-slate-700">
                          <div className="flex items-center justify-between">
                            <div>
                              <span className="font-semibold text-slate-200">Ready to Launch</span>
                              <p className="text-sm text-slate-400">Your dashboard is generated and ready to run</p>
                            </div>
                            <Button
                              onClick={handleStartDashboard}
                              disabled={isLoading}
                              className="bg-neon-green hover:bg-neon-green/90 text-black font-semibold"
                            >
                              <Play className="w-4 h-4 mr-2" />
                              Launch Dashboard
                            </Button>
                          </div>
                        </div>
                      )}

                      {dashboardUrl && (
                        <div className="bg-slate-800/10 p-4 rounded-lg border border-slate-700">
                          <div className="flex items-center justify-between mb-2">
                            <p className="text-sm font-semibold text-slate-300">Dashboard URL:</p>
                            <Badge variant="outline" className="text-xs">Active</Badge>
                          </div>
                          <div className="flex items-center gap-2">
                            <code className="text-sm bg-slate-700/50 px-2 py-1 rounded flex-1 truncate text-slate-300">{dashboardUrl}</code>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => navigator.clipboard.writeText(dashboardUrl)}
                              className="shrink-0 bg-slate-800/50 border-slate-600"
                            >
                              <Copy className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>
                      )}

                      {/* Persistent Runtime Error Panel */}
                      {runtimeError && (
                        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                                <p className="text-sm font-semibold text-red-400">Runtime error while starting the dashboard</p>
                              </div>
                              <pre className="max-h-52 overflow-auto text-xs whitespace-pre-wrap font-mono text-red-300 bg-red-900/20 p-3 rounded border border-red-500/20">
{runtimeError}
                              </pre>
                            </div>
                            <div className="flex flex-col gap-2 ml-3">
                              <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(runtimeError)} className="bg-slate-900/50 border-red-500/40 text-red-200">Copy</Button>
                              <Button variant="default" size="sm" onClick={handleAttemptFix} className="bg-red-500 hover:bg-red-600 text-white">Attempt Auto-Fix</Button>
                            </div>
                          </div>
                          <p className="text-[11px] text-red-300/80 mt-2">We’ll send this error to the AI auto-fix pipeline and update the code automatically.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Enhanced Error Display */}
                  {dashboardStatus.status === 'failed' && dashboardStatus.error && (
                    <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
                      <div className="flex items-start gap-3">
                        <div className="w-5 h-5 bg-red-500 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                          <span className="text-white text-xs font-bold">!</span>
                        </div>
                        <div className="flex-1">
                          <p className="text-red-600 font-semibold mb-1">Generation Failed</p>
                          <p className="text-sm text-red-500">{dashboardStatus.error}</p>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleSubmit}
                            className="mt-3 hover:border-red-400"
                          >
                            Try Again
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            </section>
          )}

          {/* Right-side Sliding Sidebar for Preview and Code */}
          <>
            {/* Backdrop */}
            <div
              className={`fixed inset-0 z-40 bg-black/40 transition-opacity ${isSidebarOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
              onClick={() => setIsSidebarOpen(false)}
              aria-hidden={!isSidebarOpen}
            />
            {/* Sidebar Panel */}
            <aside
              className={`fixed top-0 right-0 z-50 h-full w-full sm:w-[520px] lg:w-[760px] bg-gradient-to-b from-slate-900/95 to-slate-950/95 border-l border-slate-700/50 backdrop-blur-xl shadow-2xl transform transition-transform duration-300 ${isSidebarOpen ? 'translate-x-0' : 'translate-x-full'}`}
              role="complementary"
              aria-label="Dashboard preview and code"
            >
              {/* Header with Tabs */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50 bg-slate-900/80">
                <div className="flex items-center gap-3">
                  {/* macOS traffic lights */}
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]" />
                    <span className="w-3 h-3 rounded-full bg-yellow-400 shadow-[0_0_8px_rgba(250,204,21,0.6)]" />
                    <span className="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
                  </div>
                  <span className="text-xs text-slate-400 font-mono">Veridia — Dashboard</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant={activeSidebarTab === 'preview' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => handleSidebarTabChange('preview')}
                    className={`${activeSidebarTab === 'preview' ? 'bg-neon-cyan text-black' : 'bg-slate-800/60 border-slate-600 text-slate-200'}`}
                    disabled={!dashboardUrl}
                  >
                    <Eye className="w-4 h-4 mr-2" /> Preview
                  </Button>
                  <Button
                    variant={activeSidebarTab === 'code' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => handleSidebarTabChange('code')}
                    className={`${activeSidebarTab === 'code' ? 'bg-neon-purple text-white' : 'bg-slate-800/60 border-slate-600 text-slate-200'}`}
                    disabled={!dashboardId}
                  >
                    <Code className="w-4 h-4 mr-2" /> Code
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setIsSidebarOpen(false)} className="bg-slate-800/60 border-slate-600 text-slate-200">Close</Button>
                </div>
              </div>

              {/* Sub-header actions */}
              <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/60 bg-slate-950/40">
                <div className="flex items-center gap-3 text-xs text-slate-400">
                  <span className="w-2 h-2 bg-neon-blue rounded-full animate-pulse" />
                  <span>{activeSidebarTab === 'preview' ? 'Live Dashboard' : 'Generated Python Code'}</span>
                </div>
                <div className="flex items-center gap-2">
                  {activeSidebarTab === 'code' && (
                    <>
                      <Button variant="outline" size="sm" onClick={handleCopyCode} className="bg-slate-800/60 border-slate-600 text-slate-200"><Copy className="w-4 h-4 mr-1" />{codeCopied ? 'Copied' : 'Copy'}</Button>
                      <Button variant="outline" size="sm" onClick={handleDownloadCode} className="bg-slate-800/60 border-slate-600 text-slate-200"><Download className="w-4 h-4 mr-1" />Download</Button>
                      {!isEditingCode ? (
                        <Button variant="outline" size="sm" onClick={handleStartEditing} className="bg-slate-800/60 border-slate-600 text-slate-200">Edit</Button>
                      ) : (
                        <Button variant="outline" size="sm" onClick={handleCancelEditing} className="bg-slate-800/60 border-slate-600 text-slate-200">Cancel</Button>
                      )}
                      <Button variant="default" size="sm" onClick={handleRerunCode} disabled={isRerunning || !dashboardId} className="bg-neon-cyan text-black">
                        <Play className="w-4 h-4 mr-1" /> {isRerunning ? 'Rerunning…' : 'Rerun Code'}
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {/* Content */}
              <div className="h-[calc(100%-92px)] overflow-hidden">
                {activeSidebarTab === 'preview' ? (
                  <div className="w-full h-full p-2">
                    {dashboardUrl ? (
                      <div className="w-full h-full rounded-xl overflow-hidden border border-slate-700 bg-slate-900 shadow-[0_0_40px_rgba(34,197,94,0.08)]">
                        {/* mac-like window bar */}
                        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800 bg-gradient-to-r from-slate-900 to-slate-800">
                          <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                          <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                          <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                          <span className="ml-3 text-xs text-slate-400 font-mono">Dashboard Preview</span>
                        </div>
                        <iframe title="Dashboard Preview" src={dashboardUrl} className="w-full h-[calc(100%-36px)]" />
                      </div>
                    ) : (
                      <div className="h-full flex items-center justify-center text-slate-400">No preview available</div>
                    )}
                  </div>
                ) : (
                  <div className="h-full flex flex-col">
                    <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700 bg-slate-900/60">
                      <div className="flex items-center gap-2 text-slate-300">
                        <Code className="w-4 h-4" />
                        <span className="font-mono text-xs">dashboard_{dashboardId}.py</span>
                      </div>
                      <Badge variant="secondary" className="bg-neon-purple/20 text-neon-purple border-neon-purple/30">Python 3.8+</Badge>
                    </div>
                    <div className="flex-1 overflow-auto">
                      {isCodeLoading ? (
                        <div className="h-full flex items-center justify-center text-slate-400">
                          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading code...
                        </div>
                      ) : isEditingCode ? (
                        <div className="h-full rounded-xl overflow-hidden border border-slate-800 bg-gradient-to-b from-slate-950 to-slate-900">
                          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800 bg-gradient-to-r from-slate-900 to-slate-800">
                            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                            <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                            <span className="ml-3 text-xs text-slate-400 font-mono">Editing Code</span>
                          </div>
                          <textarea
                            className="w-full h-[calc(100%-36px)] bg-transparent text-slate-100 p-4 text-xs md:text-sm font-mono leading-relaxed outline-none resize-none"
                            spellCheck={false}
                            value={editedCode}
                            onChange={(e) => setEditedCode(e.target.value)}
                            onKeyDown={handleEditorKeyDown}
                          />
                        </div>
                      ) : generatedCode ? (
                        <div className="h-full rounded-xl overflow-hidden border border-slate-800 bg-gradient-to-b from-slate-950 to-slate-900">
                          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800 bg-gradient-to-r from-slate-900 to-slate-800">
                            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                            <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                            <span className="ml-3 text-xs text-slate-400 font-mono">Generated Code</span>
                          </div>
                          <pre className="bg-transparent text-slate-100 p-4 overflow-x-auto text-xs md:text-sm font-mono leading-relaxed max-h-full">
                            <code className="language-python">
                              {generatedCode.split('\n').map((line, index) => (
                                <div key={index} className="flex">
                                  <span className="text-slate-500 select-none w-10 md:w-12 text-right pr-3 md:pr-4 shrink-0">
                                    {(index + 1).toString().padStart(3, ' ')}
                                  </span>
                                  <span className="flex-1">{line.replace(/\t/g, '    ')}</span>
                                </div>
                              ))}
                            </code>
                          </pre>
                        </div>
                      ) : (
                        <div className="h-full flex items-center justify-center text-slate-400">No code loaded</div>
                      )}
                    </div>
                    {generatedCode && (
                      <div className="px-4 py-2 border-t border-slate-700 bg-slate-900/60 text-xs text-slate-400 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span>📦 Self-contained</span>
                          <span>🔧 Production Ready</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span>{generatedCode.split('\n').length} lines</span>
                          <span>•</span>
                          <span>{Math.round(generatedCode.length / 1024)}KB</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </aside>

            {/* Floating open toggle when closed */}
            {!isSidebarOpen && (isDashboardRunning || generatedCode) && (
              <button
                aria-label="Open preview/code panel"
                onClick={() => setIsSidebarOpen(true)}
                className="fixed right-3 top-1/2 -translate-y-1/2 z-30 group"
              >
                <div className="flex items-center gap-2 bg-slate-900/80 border border-slate-700/70 backdrop-blur-md text-slate-200 rounded-full px-3 py-2 shadow-lg hover:shadow-neon-blue/20 hover:border-neon-blue/40 transition-all">
                  <span className="text-xs font-mono hidden sm:block">{generatedCode ? 'Preview / Code' : 'Preview'}</span>
                  <ChevronRight className="w-4 h-4 text-neon-cyan group-hover:translate-x-0.5 transition-transform" />
                </div>
              </button>
            )}
          </>
        </main>

        {/* Examples Section */}
        <VideoInspirationGallery onExampleSelect={handleExamplePrompt} onUseTemplate={handleUseTemplate} />

        {/* Footer */}
        <footer className="text-center py-12 border-t border-slate-700/50 bg-slate-900/20">
          <div className="flex flex-col items-center gap-6">
            <div className="flex items-center gap-4">
              <img src={vizAiLogo} alt="Veridia" className="w-10 h-10" />
              <span className="font-orbitron font-bold text-2xl gradient-text">Veridia</span>
            </div>
            <div className="text-center space-y-2">
              <div className="flex items-center justify-center gap-2 text-slate-300 text-sm">
                <span>Crafted by</span>
                <span className="font-semibold text-neon-cyan">Shreya Aggarwal</span>
                <span>•</span>
                <span>Powered by Advanced AI</span>
              </div>
              <div className="flex items-center justify-center gap-4 text-xs text-slate-400">
                <span>Enterprise-grade visualization platform</span>
                <Github className="w-4 h-4 hover:text-neon-blue cursor-pointer transition-colors" />
              </div>
            </div>
            <div className="text-center text-xs text-slate-500 max-w-md">
              Transform your data into professional, interactive dashboards with the power of AI.
              No coding knowledge required.
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default DataVisualizationAgent;