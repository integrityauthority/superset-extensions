const path = require("path");
const { ModuleFederationPlugin } = require("webpack").container;
const packageConfig = require("./package");

module.exports = (env, argv) => {
  const isProd = argv.mode === "production";

  return {
    entry: isProd ? {} : "./src/index.tsx",
    mode: isProd ? "production" : "development",
    devServer: {
      port: 3000,
      headers: {
        "Access-Control-Allow-Origin": "*",
      },
    },
    output: {
      clean: true,
      filename: isProd ? undefined : "[name].[contenthash].js",
      chunkFilename: "[name].[contenthash].js",
      path: path.resolve(__dirname, "dist"),
      publicPath: "/api/v1/extensions/integrityauthority/vambery-ai-assistant/",
    },
    resolve: {
      extensions: [".ts", ".tsx", ".js", ".jsx"],
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          use: "ts-loader",
          exclude: /node_modules/,
        },
      ],
    },
    plugins: [
      new ModuleFederationPlugin({
        name: "vambery_ai_assistant",
        filename: "remoteEntry.[contenthash].js",
        exposes: {
          "./index": "./src/index.tsx",
        },
        shared: {
          react: {
            singleton: true,
            requiredVersion: packageConfig.peerDependencies.react,
            import: false,
          },
          "react-dom": {
            singleton: true,
            requiredVersion: packageConfig.peerDependencies["react-dom"],
            import: false,
          },
          antd: {
            singleton: true,
            requiredVersion: packageConfig.peerDependencies["antd"],
            import: false,
          },
          // Consumed from the host's share scope, as the 7.0 extension template
          // does: that instance carries this extension's getContext(). Hosts
          // that share nothing (6.1) get the window.superset fallback instead.
          "@apache-superset/core": {
            singleton: true,
            requiredVersion: false,
            version: "0.0.0",
            shareKey: "@apache-superset/core",
            import: path.resolve(__dirname, "src/supersetCoreFallback.js"),
          },
        },
      }),
    ],
  };
};
