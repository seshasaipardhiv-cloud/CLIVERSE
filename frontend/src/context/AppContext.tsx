import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { SystemHealth, ProjectsResponse, ActivityItem } from "../types";
import { systemApi } from "../api/system";
import { activityApi } from "../api/activity";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "warn" | "info";
  title: string;
  message?: string;
}

interface AppContextType {
  health: SystemHealth | null;
  projectsData: ProjectsResponse | null;
  currentProject: string;
  currentCli: string;
  recentActivities: ActivityItem[];
  isLoading: boolean;
  toasts: ToastMessage[];
  showToast: (toast: Omit<ToastMessage, "id">) => void;
  dismissToast: (id: string) => void;
  setCurrentProject: (id: string) => Promise<void>;
  setCurrentCli: (cli: string) => Promise<void>;
  refreshHealth: () => Promise<void>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [projectsData, setProjectsData] = useState<ProjectsResponse | null>(null);
  const [currentProject, setProjectState] = useState<string>("cliverse-core");
  const [currentCli, setCliState] = useState<string>("claude-cli");
  const [recentActivities, setRecentActivities] = useState<ActivityItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = useCallback((t: Omit<ToastMessage, "id">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`;
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 4500);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const [h, p] = await Promise.all([
        systemApi.getHealth(),
        systemApi.getProjects(),
      ]);
      setHealth(h);
      setProjectsData(p);
      if (p.active_project) setProjectState(p.active_project);
      if (p.active_cli) setCliState(p.active_cli);
    } catch (err) {
      console.error("Failed to load system health:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setCurrentProject = useCallback(async (newProjectId: string) => {
    try {
      await systemApi.selectProject(newProjectId, currentCli);
      setProjectState(newProjectId);
      showToast({
        type: "success",
        title: "Project Switched",
        message: `Active workspace is now '${newProjectId}'`,
      });
      await refreshHealth();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Project Switch Failed",
        message: err instanceof Error ? err.message : "Error switching project",
      });
    }
  }, [currentCli, refreshHealth, showToast]);

  const setCurrentCli = useCallback(async (newCli: string) => {
    try {
      await systemApi.selectProject(currentProject, newCli);
      setCliState(newCli);
      showToast({
        type: "info",
        title: "Target CLI Changed",
        message: `Active CLI is now '${newCli}'`,
      });
      await refreshHealth();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "CLI Switch Failed",
        message: err instanceof Error ? err.message : "Error switching CLI",
      });
    }
  }, [currentProject, refreshHealth, showToast]);

  // Initial load and periodic heartbeat
  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 8000);
    return () => clearInterval(interval);
  }, [refreshHealth]);

  // Initial activities + SSE stream
  useEffect(() => {
    activityApi.list(30).then(setRecentActivities).catch(() => {});

    const unsubscribe = activityApi.subscribe((newEvent) => {
      setRecentActivities((prev) => [newEvent, ...prev.slice(0, 49)]);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  return (
    <AppContext.Provider
      value={{
        health,
        projectsData,
        currentProject,
        currentCli,
        recentActivities,
        isLoading,
        toasts,
        showToast,
        dismissToast,
        setCurrentProject,
        setCurrentCli,
        refreshHealth,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
};
