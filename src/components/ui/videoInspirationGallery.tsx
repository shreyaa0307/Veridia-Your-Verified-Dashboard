import React, { useState, useRef } from 'react';
import { ChevronLeft, ChevronRight, X, Play, Pause, Globe, Heart, Thermometer, Car, TrendingUp, Eye, Download } from 'lucide-react';
// Import thumbnails from src/assets so they bundle correctly
import worldImg from '@/assets/world.png';
import medicalImg from '@/assets/medical.png';
import marketingImg from '@/assets/marketing.png';
import transportImg from '@/assets/transport.png';
import fintechImg from '@/assets/fintech.png';
import worldVideo from '@/assets/video_world_dash.mp4';
import medicalVideo from '@/assets/video_medical.mp4';
import marketingVideo from '@/assets/video_marketing.mp4';
import transportVideo from '@/assets/video_transport.mp4';
import fintechVideo from '@/assets/video_fintech.mp4';

type UseTemplatePayload = { prompt: string; dataset: string };
type Props = {
  onExampleSelect?: (prompt: string, dataset?: string) => void;
  onUseTemplate?: (payload: UseTemplatePayload) => void;
};

const VideoInspirationGallery: React.FC<Props> = ({ onExampleSelect, onUseTemplate }) => {
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const scrollContainerRef = useRef(null);
  const videoRef = useRef(null);
  // Removed auto-scroll for performance; manual scroll via buttons only

  const dashboardExamples = [
    {
      id: 1,
      title: "World Environment Dashboard",
      category: "Environmental Analytics",
      icon: Globe,
      videoUrl: worldVideo,
      thumbnail: worldImg,
      dataset: "world_environment_synthetic.csv",
      description: "VizAI intelligently selected choropleth maps, animated time series, scatter plots, and trend charts to reveal patterns in GDP, CO₂ emissions, and life expectancy across countries.",
      features: ["Interactive World Map", "Animated Time Series", "Dynamic Filtering", "CO₂ Correlation Analysis"],
      color: "from-emerald-500/20 to-cyan-500/20",
      borderColor: "border-emerald-500/30",
      accentColor: "text-cyan-400"
    },
    {
      id: 2,
      title: "Medical Dataset Dashboard",
      category: "Healthcare Analytics",
      icon: Heart,
      videoUrl: medicalVideo,
      thumbnail: medicalImg,
      dataset: "synthetic_medical_data.csv",
      description: "VizAI generated 3D scatter plots, Sankey diagrams, hierarchical charts, and bar plots to capture complex relationships in patient data.",
      features: ["3D Health Correlations", "Patient Flow Diagrams", "Real-time Insights", "Medical Trend Analysis"],
      color: "from-rose-500/20 to-pink-500/20",
      borderColor: "border-rose-500/30",
      accentColor: "text-rose-400"
    },
    {
      id: 3,
      title: "Fintech Behavioral Dashboard",
      category: "Fintech Analytics",
      icon: Thermometer,
      videoUrl: fintechVideo,
      thumbnail: fintechImg,
      dataset: "fintech_behavioral.csv",
      description: "VizAI automatically chose sunburst, scatter plots, 3D plots, and time series to visualize behavioral patterns in fintech users.",
      features: ["Sunburst Visualization", "3D Scatter Plots", "Real-time Insights", "Fintech Trend Analysis"],
      color: "from-amber-500/20 to-yellow-500/20",
      borderColor: "border-amber-500/30",
      accentColor: "text-amber-400"
    },
    {
      id: 4,
      title: "Transportation Dashboard",
      category: "Logistics Analytics",
      icon: Car,
      videoUrl: transportVideo,
      thumbnail: transportImg,
      dataset: "synthetic_transportation_data.csv",
      description: "VizAI crafted choropleths, time series, 3D scatter plots, and Sankey flow diagrams to reveal revenue trends and efficiency metrics.",
      features: ["Route Optimization", "Real-time Delay Tracking", "Revenue Analytics", "Passenger Flow Analysis"],
      color: "from-blue-500/20 to-indigo-500/20",
      borderColor: "border-blue-500/30",
      accentColor: "text-blue-400"
    },
    {
      id: 5,
      title: "Marketing Analytics Dashboard",
      category: "Business Intelligence",
      icon: TrendingUp,
      videoUrl: marketingVideo,
      thumbnail: marketingImg,
      dataset: "marketing_data_countries.csv",
      description: "VizAI created Sankey diagrams, 3D scatter plots, choropleth maps, and time series for marketing campaign analysis.",
      features: ["Campaign ROI Analysis", "Customer Journey Mapping", "Channel Performance", "Geographic Targeting"],
      color: "from-purple-500/20 to-violet-500/20",
      borderColor: "border-purple-500/30",
      accentColor: "text-purple-400"
    }
  ];

  // Auto-scroll removed; no hover handlers needed

  const scrollLeft = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollBy({ left: -350, behavior: 'smooth' });
    }
  };

  const scrollRight = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollBy({ left: 350, behavior: 'smooth' });
    }
  };

  const openVideoModal = (example) => {
    setSelectedVideo(example);
    setIsPlaying(false);
  };

  const closeModal = () => {
    setSelectedVideo(null);
    setIsPlaying(false);
    if (videoRef.current) {
      videoRef.current.pause();
    }
  };

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const downloadDataset = (filename: string) => {
    // Use the same proxied API base as the frontend uses elsewhere
    const base = import.meta.env.VITE_API_BASE_URL || '/api';
    const link = document.createElement('a');
    link.href = `${base}/data/${encodeURIComponent(filename)}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <section className="mb-16 max-w-7xl mx-auto px-6">
      <div className="text-center mb-12">
        <h2 className="text-4xl font-bold mb-4 bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
          ✨ Live Dashboard Gallery
        </h2>
        <p className="text-slate-400 max-w-3xl mx-auto text-lg leading-relaxed">
          Watch real dashboards in action. Each video showcases fully interactive, production-ready visualizations 
          with dynamic filtering, animations, and professional insights panels - all generated automatically by VizAI.
        </p>
      </div>

      {/* Video Gallery Container */}
      <div className="relative group">
        {/* Scroll Buttons */}
        <button
          onClick={scrollLeft}
          className="absolute left-4 top-1/2 transform -translate-y-1/2 z-10 bg-slate-800/90 backdrop-blur-sm border border-slate-600 rounded-full p-3 text-white hover:bg-slate-700/90 transition-all duration-300 opacity-0 group-hover:opacity-100"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>

        <button
          onClick={scrollRight}
          className="absolute right-4 top-1/2 transform -translate-y-1/2 z-10 bg-slate-800/90 backdrop-blur-sm border border-slate-600 rounded-full p-3 text-white hover:bg-slate-700/90 transition-all duration-300 opacity-0 group-hover:opacity-100"
        >
          <ChevronRight className="w-6 h-6" />
        </button>

        {/* Scrollable Container */}
        <div
          ref={scrollContainerRef}
          className="flex gap-6 overflow-x-auto scrollbar-hide pb-4"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {dashboardExamples.map((example) => (
            <div
              key={example.id}
              className={`flex-shrink-0 w-96 h-[28rem] bg-gradient-to-br ${example.color} backdrop-blur-sm border ${example.borderColor} rounded-2xl overflow-hidden hover:scale-105 transition-all duration-500 cursor-pointer group/card hover:shadow-2xl hover:shadow-blue-500/10`}
              onClick={() => openVideoModal(example)}
            >
              {/* Video Thumbnail */}
              <div className="relative overflow-hidden h-56">
                <img
                  src={example.thumbnail}
                  alt={example.title}
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full object-cover group-hover/card:scale-110 transition-transform duration-500"
                />
                
                {/* Play Button Overlay */}
                <div className="absolute inset-0 bg-black/50 flex items-center justify-center opacity-0 group-hover/card:opacity-100 transition-opacity duration-300">
                  <div className="w-16 h-16 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center border border-white/30">
                    <Play className="w-8 h-8 text-white ml-1" />
                  </div>
                </div>

                {/* Category Badge */}
                <div className="absolute top-4 right-4 px-3 py-1 bg-slate-900/80 backdrop-blur-sm rounded-full text-xs font-medium text-cyan-400 border border-cyan-400/30">
                  {example.category}
                </div>

                {/* Icon */}
                <div className="absolute top-4 left-4 w-10 h-10 bg-slate-800/80 backdrop-blur-sm rounded-full flex items-center justify-center border border-slate-600/50">
                  <example.icon className="w-5 h-5 text-white" />
                </div>
              </div>

              {/* Content */}
              <div className="p-6">
                <h3 className={`text-xl font-bold text-white mb-3 group-hover/card:${example.accentColor} transition-colors`}>
                  {example.title}
                </h3>

                <p className="text-slate-300 text-sm leading-relaxed mb-4 line-clamp-3">
                  {example.description}
                </p>

                {/* Features */}
                <div className="flex flex-wrap gap-2 mb-4">
                  {example.features.slice(0, 2).map((feature, index) => (
                    <span
                      key={index}
                      className="px-2 py-1 bg-slate-800/50 rounded-md text-xs text-slate-300 border border-slate-600/30"
                    >
                      {feature}
                    </span>
                  ))}
                  {example.features.length > 2 && (
                    <span className="px-2 py-1 bg-slate-700/50 rounded-md text-xs text-slate-400">
                      +{example.features.length - 2} more
                    </span>
                  )}
                </div>

                {/* Watch Button */}
                <div className="flex items-center justify-between">
                  <button className="flex items-center gap-2 text-cyan-400 hover:text-cyan-300 transition-colors text-sm font-medium">
                    <Eye className="w-4 h-4" />
                    Watch Demo
                  </button>
                  <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                </div>
              </div>

              {/* Glow Effect */}
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-blue-500/5 to-purple-500/5 opacity-0 group-hover/card:opacity-100 transition-opacity duration-500 pointer-events-none" />
            </div>
          ))}
        </div>

        {/* Fade Edges */}
        <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-slate-950 to-transparent pointer-events-none" />
        <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent pointer-events-none" />
      </div>

      {/* Video Modal */}
      {selectedVideo && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-800 rounded-2xl max-w-6xl w-full max-h-[90vh] overflow-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-slate-700">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-slate-700 rounded-full flex items-center justify-center">
                  <selectedVideo.icon className="w-6 h-6 text-cyan-400" />
                </div>
                <div>
                  <h3 className="text-2xl font-bold text-white">{selectedVideo.title}</h3>
                  <p className="text-slate-400">{selectedVideo.category}</p>
                </div>
              </div>
              <button
                onClick={closeModal}
                className="w-10 h-10 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
              >
                <X className="w-5 h-5 text-white" />
              </button>
            </div>

            <div className="p-6">
              {/* Video Player */}
              <div className="relative mb-6 rounded-xl overflow-hidden bg-slate-900 max-h-[70vh]">
                <div className="aspect-video w-full h-96 flex items-center justify-center">
                  <video
                    ref={videoRef}
                    className="w-full h-full max-h-[60vh] object-contain"
                    poster={selectedVideo.thumbnail}
                    preload="none"
                    playsInline
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                  >
                    <source src={selectedVideo.videoUrl} type="video/mp4" />
                    Your browser does not support the video tag.
                  </video>
                </div>
                
                {/* Video Controls */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <button
                    onClick={togglePlay}
                    className="w-20 h-20 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center border border-white/30 hover:bg-white/30 transition-colors"
                  >
                    {isPlaying ? (
                      <Pause className="w-10 h-10 text-white" />
                    ) : (
                      <Play className="w-10 h-10 text-white ml-2" />
                    )}
                  </button>
                </div>
              </div>

              {/* Details */}
              <div className="grid md:grid-cols-2 gap-6">
                <div>
                  <h4 className="text-lg font-semibold text-white mb-3">Dataset</h4>
                  <div className="flex items-center gap-3 bg-slate-900/50 p-3 rounded-lg">
                    <div className="flex-1">
                      <p className="text-slate-300 text-sm font-mono truncate">
                        {selectedVideo.dataset}
                      </p>
                    </div>
                    <button 
                      onClick={() => downloadDataset(selectedVideo.dataset)}
                      className="flex items-center gap-2 px-3 py-2 bg-blue-500/20 hover:bg-blue-500/30 border border-blue-500/30 rounded-md text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      Download
                    </button>
                  </div>
                </div>

                <div>
                  <h4 className="text-lg font-semibold text-white mb-3">Key Features</h4>
                  <div className="flex flex-wrap gap-2">
                    {selectedVideo.features.map((feature, index) => (
                      <span
                        key={index}
                        className="px-3 py-1 bg-slate-700/50 rounded-full text-sm text-slate-300 border border-slate-600/30"
                      >
                        {feature}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-6">
                <h4 className="text-lg font-semibold text-white mb-3">AI Analysis & Visualization</h4>
                <p className="text-slate-300 leading-relaxed">
                  {selectedVideo.description}
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-4 mt-6 pt-6 border-t border-slate-700">
                <button
                  onClick={() => {
                    // Prefer structured callback for auto-upload. Fallback to simple prompt setter.
                    if (onUseTemplate) {
                      onUseTemplate({ prompt: selectedVideo.title, dataset: selectedVideo.dataset });
                    } else {
                      onExampleSelect?.(selectedVideo.title, selectedVideo.dataset);
                    }
                    closeModal();
                  }}
                  className="flex-1 bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 text-white px-6 py-3 rounded-lg font-medium transition-all duration-300"
                >
                  Use This Template
                </button>
                <button 
                  onClick={() => downloadDataset(selectedVideo.dataset)}
                  className="flex items-center gap-2 px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
                >
                  <Download className="w-5 h-5" />
                  Download Dataset
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

export default VideoInspirationGallery;