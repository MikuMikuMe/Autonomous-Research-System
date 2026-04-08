import React from "react";

interface Props {
  report: string | null;
}

export const ReportView: React.FC<Props> = ({ report }) => {
  if (!report) return null;

  return (
    <div className="report-view">
      <h3>Report</h3>
      <pre className="report-view__content">{report}</pre>
    </div>
  );
};
